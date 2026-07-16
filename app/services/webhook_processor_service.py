from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.email.recipients import normalize_address
from app.integrations.microsoft_graph.client import GraphClient
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.integrations.microsoft_graph.models import GraphMessage, Recipient
from app.integrations.microsoft_graph.rich_notifications import (
    RichNotificationError,
    decrypt_encrypted_content,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import EmailInput
from app.schemas.subscription import WebhookNotificationItem, WebhookNotificationPayload
from app.services.bot_service import get_bot_service
from app.services.email_analysis import Analyzer
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

_dev_analyze = None


def set_dev_analyze(fn) -> None:
    global _dev_analyze
    _dev_analyze = fn


class WebhookProcessorService:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        analyzer: Analyzer,
    ):
        self._graph = GraphClient(http_client)
        self._analyzer = analyzer

    async def process_notification(self, payload: WebhookNotificationPayload) -> int:
        if not settings.webhook_client_state:
            logger.warning("WEBHOOK_CLIENT_STATE is not configured; ignoring notifications")
            return 0

        if settings.webhook_include_resource_data and payload.validation_tokens is None:
            logger.warning(
                "Rich notification missing validationTokens (often means Graph Change Tracking "
                "app role assignment is misconfigured); continuing with clientState check"
            )

        db = SessionLocal()
        try:
            subscription_repo = SubscriptionRepository(db)
            task_service = TaskService(
                TaskRepository(db),
                UserRepository(db),
                get_bot_service(),
                TaskStatusHistoryRepository(db),
            )
            processed = 0
            for item in payload.value:
                processed += await self._process_item(item, subscription_repo, task_service)
            return processed
        finally:
            db.close()

    async def _process_item(
        self,
        item: WebhookNotificationItem,
        subscription_repo: SubscriptionRepository,
        task_service: TaskService,
    ) -> int:
        if item.client_state != settings.webhook_client_state:
            logger.warning("Ignoring notification with invalid clientState")
            return 0

        subscription = subscription_repo.get_by_id(item.subscription_id)
        if not subscription or not subscription.user or subscription.user.is_deleted:
            logger.warning("Unknown or deleted subscription id: %s", item.subscription_id)
            return 0

        message_id = self._resolve_message_id(item)
        if not message_id:
            logger.warning(
                "Could not resolve message id from notification for subscription %s",
                item.subscription_id,
            )
            return 0

        try:
            message = await self._load_whitelisted_message(
                item,
                graph_user_id=subscription.graph_user_id,
                message_id=message_id,
                mailbox_email=subscription.user.email,
            )
            if message is None:
                return 0

            parsed = parse_graph_message(
                message,
                user_email=subscription.user.email,
                user_id=str(subscription.user_id),
            )
            email_input = EmailInput.model_validate(parsed.model_dump())
            logger.info("Email input: %s", email_input)

            if _dev_analyze is not None:
                analysis = await _dev_analyze(self._analyzer, email_input, parsed)
            else:
                analysis = await self._analyzer.analyze(email_input)

            logger.info("Email analysis result: %s", analysis.model_dump_json())

            task = await task_service.apply_analysis(analysis, parsed, parsed.from_address)
            if task is not None:
                logger.info("Task %s %s from email %s", task.id, analysis.action.value, message_id)
            return 1
        except Exception as exc:
            logger.warning(
                "Failed to fetch or parse message %s for user %s: %s",
                message_id,
                subscription.graph_user_id,
                exc,
            )
            return 0

    async def _load_whitelisted_message(
        self,
        item: WebhookNotificationItem,
        *,
        graph_user_id: str,
        message_id: str,
        mailbox_email: str,
    ) -> GraphMessage | None:
        """
        Rich payload is used only for participant identification (whitelist).
        Full message content (body, quoted parent/forward text) always comes
        from Graph GET after the whitelist check passes.
        """
        identity = (
            self._message_from_rich_notification(item)
            if settings.webhook_include_resource_data
            else None
        )
        if settings.webhook_include_resource_data and identity is None:
            logger.info(
                "No usable encryptedContent for message %s; Graph GET for whitelist check",
                message_id,
            )

        # Basic mode / decrypt failure: need Graph just to know participants.
        if identity is None:
            identity = await self._graph.get_message(graph_user_id, message_id)
            if not self._passes_email_whitelist(identity):
                logger.info("Skipping message %s - no whitelist address involved", message_id)
                return None
            return identity

        if not self._passes_email_whitelist(identity):
            logger.info("Skipping message %s - no whitelist address involved", message_id)
            return None

        logger.info(
            "Whitelist matched for message %s; Graph GET for full content",
            message_id,
        )
        return await self._graph.get_message(graph_user_id, message_id)

    def _message_from_rich_notification(
        self, item: WebhookNotificationItem
    ) -> GraphMessage | None:
        content = item.encrypted_content
        if content is None:
            return None
        if not settings.graph_notification_private_key:
            logger.warning("Missing GRAPH_NOTIFICATION_PRIVATE_KEY; cannot decrypt rich payload")
            return None
        if (
            content.encryption_certificate_id
            and settings.graph_notification_certificate_id
            and content.encryption_certificate_id != settings.graph_notification_certificate_id
        ):
            logger.warning(
                "encryptionCertificateId mismatch: got %s, configured %s",
                content.encryption_certificate_id,
                settings.graph_notification_certificate_id,
            )
            return None
        try:
            decrypted = decrypt_encrypted_content(
                data=content.data,
                data_key=content.data_key,
                data_signature=content.data_signature,
                private_key_pem=settings.graph_notification_private_key,
            )
            if "id" not in decrypted and item.resource_data and item.resource_data.id:
                decrypted["id"] = item.resource_data.id
            return GraphMessage.from_graph_response(decrypted)
        except RichNotificationError as exc:
            logger.warning("Failed to decrypt rich notification: %s", exc)
            return None

    @staticmethod
    def _resolve_message_id(item: WebhookNotificationItem) -> str | None:
        if item.resource_data and item.resource_data.id:
            return item.resource_data.id
        if item.resource:
            return item.resource.rstrip("/").split("/")[-1].split("?")[0] or None
        return None

    @staticmethod
    def _from_address(message: GraphMessage) -> str | None:
        if not message.from_recipient or not message.from_recipient.email_address:
            return None
        return normalize_address(message.from_recipient.email_address.address)

    @staticmethod
    def _addresses(recipients: list[Recipient]) -> list[str]:
        return [
            normalized
            for recipient in recipients
            if recipient.email_address
            and recipient.email_address.address
            and (normalized := normalize_address(recipient.email_address.address))
        ]

    @classmethod
    def _participant_addresses(cls, message: GraphMessage) -> set[str]:
        return {
            addr
            for addr in (
                cls._from_address(message),
                *cls._addresses(message.to_recipients),
                *cls._addresses(message.cc_recipients),
                *cls._addresses(message.bcc_recipients),
            )
            if addr
        }

    @classmethod
    def _passes_email_whitelist(cls, message: GraphMessage) -> bool:
        whitelist = settings.llm_email_whitelist
        if not whitelist:
            return True
        return bool(cls._participant_addresses(message) & whitelist)
