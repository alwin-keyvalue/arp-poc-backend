from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.email.recipients import normalize_address
from app.integrations.microsoft_graph.client import GraphClient
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.integrations.microsoft_graph.models import GraphMessage, MessageBody
from app.integrations.microsoft_graph.rich_notifications import (
    RichNotificationError,
    decrypt_encrypted_content,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import EmailInput
from app.schemas.parsed_email import ParsedEmailInput
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
                TaskRepository(db), UserRepository(db), get_bot_service(), TaskStatusHistoryRepository(db)
            )
            processed_count = 0

            for item in payload.value:
                if item.client_state != settings.webhook_client_state:
                    logger.warning("Ignoring notification with invalid clientState")
                    continue

                subscription = subscription_repo.get_by_id(item.subscription_id)
                if not subscription or not subscription.user or subscription.user.is_deleted:
                    logger.warning("Unknown or deleted subscription id: %s", item.subscription_id)
                    continue

                message_id = self._resolve_message_id(item)
                if not message_id:
                    logger.warning(
                        "Could not resolve message id from notification for subscription %s",
                        item.subscription_id,
                    )
                    continue

                try:
                    message = await self._load_message(
                        item,
                        graph_user_id=subscription.graph_user_id,
                        message_id=message_id,
                    )
                    parsed = parse_graph_message(
                        message,
                        user_email=subscription.user.email,
                        user_id=str(subscription.user_id),
                    )
                    if not self._is_whitelisted_for_llm(parsed):
                        logger.info(
                            "Skipping LLM for message %s — no whitelist address involved "
                            "(from=%s to=%s cc=%s mailbox=%s)",
                            message_id,
                            parsed.from_address,
                            parsed.to,
                            parsed.cc,
                            parsed.user_email,
                        )
                        continue

                    email_input = EmailInput.model_validate(parsed.model_dump())
                    logger.info("Email input: %s", email_input)
                    if _dev_analyze is not None:
                        analysis = await _dev_analyze(self._analyzer, email_input, parsed)
                    else:
                        analysis = await self._analyzer.analyze(email_input)

                    processed_count += 1
                    logger.info(
                        "Processed message %s for %s (kind=%s)",
                        message_id,
                        subscription.user.email,
                        parsed.kind.value,
                    )
                    logger.info(
                        "Email analysis result: %s",
                        analysis.model_dump_json(),
                    )
                    task = await task_service.apply_analysis(
                        analysis,
                        parsed,
                        parsed.from_address,
                    )
                    if task is not None:
                        logger.info("Task %s %s from email %s", task.id, analysis.action.value, message_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch or parse message %s for user %s: %s",
                        message_id,
                        subscription.graph_user_id,
                        exc,
                    )

            return processed_count
        finally:
            db.close()

    async def _load_message(
        self,
        item: WebhookNotificationItem,
        *,
        graph_user_id: str,
        message_id: str,
    ) -> GraphMessage:
        """
        basic mode: Graph GET the message.
        rich mode: decrypt encryptedContent; Outlook cannot ship Body, so use
        bodyPreview when WEBHOOK_RICH_USE_BODY_PREVIEW=true, else Graph GET.
        """
        if not settings.webhook_include_resource_data:
            return await self._graph.get_message(graph_user_id, message_id)

        rich_message = self._message_from_rich_notification(item)
        if rich_message is None:
            logger.info(
                "No usable encryptedContent for message %s; falling back to Graph GET",
                message_id,
            )
            return await self._graph.get_message(graph_user_id, message_id)

        if self._has_usable_body(rich_message):
            logger.debug("Using decrypted rich notification for message %s", message_id)
            return rich_message

        if settings.webhook_rich_use_body_preview and rich_message.body_preview:
            logger.info(
                "Rich notification for %s has no Body; using bodyPreview (set "
                "WEBHOOK_RICH_USE_BODY_PREVIEW=false to Graph-GET full body)",
                message_id,
            )
            rich_message.body = MessageBody(
                content_type="text",
                content=rich_message.body_preview,
            )
            return rich_message

        logger.info(
            "Rich notification for %s lacks body; falling back to Graph GET",
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
    def _has_usable_body(message: GraphMessage) -> bool:
        return bool(message.body and message.body.content and message.body.content.strip())

    @staticmethod
    def _is_whitelisted_for_llm(parsed: ParsedEmailInput) -> bool:
        whitelist = settings.llm_email_whitelist
        if not whitelist:
            return True

        involved = {
            normalize_address(addr)
            for addr in (
                parsed.from_address,
                parsed.user_email,
                *parsed.to,
                *parsed.cc,
                *parsed.bcc,
            )
            if addr
        }
        return bool(involved & whitelist)
