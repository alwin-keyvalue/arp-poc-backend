from __future__ import annotations

import enum
import logging
import uuid
from collections import Counter

import httpx

from app.config import settings
from app.database import SessionLocal
from app.email.classification import EmailKind
from app.email.recipients import normalize_address
from app.email.thread_context import collect_thread_ids, format_thread_context
from app.integrations.microsoft_graph.client import GraphClient
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.integrations.microsoft_graph.models import GraphMessage, Recipient
from app.integrations.microsoft_graph.rich_notifications import (
    RichNotificationError,
    decrypt_encrypted_content,
)
from app.models.task import Task
from app.repositories.processed_email_repository import ProcessedEmailRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.label_repository import LabelRepository
from app.repositories.task_change_history_repository import TaskChangeHistoryRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import EmailInput, KnownUser
from app.schemas.subscription import WebhookNotificationItem, WebhookNotificationPayload
from app.services.bot_service import get_bot_service
from app.services.conversation_service import ConversationService
from app.services.email_analysis import Analyzer
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

_WHITELIST_SKIP_MESSAGE = "Skipping message %s - no whitelist address involved"


class MessageOutcome(str, enum.Enum):
    """What happened to a single message in process_message — precise enough for callers
    (webhook and mailbox sync) to log per-run aggregate counts, not just a pass/fail total."""

    ALREADY_PROCESSED = "already_processed"
    WHITELIST_SKIPPED = "whitelist_skipped"
    HANDLED = "handled"


# _process_item can also reject a notification before it ever reaches process_message
# (bad clientState, unknown subscription, unresolvable message id, fetch/parse failure) —
# this is a distinct bucket from any MessageOutcome so batch summaries can show it separately.
_REJECTED = "rejected"


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

        if payload.validation_tokens is None:
            logger.warning(
                "Rich notification missing validationTokens (often means Graph Change Tracking "
                "app role assignment is misconfigured); continuing with clientState check"
            )

        logger.info("Processing webhook notification batch: %d item(s)", len(payload.value))

        db = SessionLocal()
        try:
            subscription_repo = SubscriptionRepository(db)
            processed_repo = ProcessedEmailRepository(db)
            user_repository = UserRepository(db)
            task_repository = TaskRepository(db)
            task_service = TaskService(
                task_repository,
                user_repository,
                get_bot_service(),
                TaskChangeHistoryRepository(db),
                LabelRepository(db),
            )
            known_users = [
                KnownUser(
                    email=u.email,
                    display_name=u.display_name,
                    coverage_topics=list(u.coverage_topics or []),
                )
                for u in user_repository.get_all(limit=1000)
            ]
            conversation_service = ConversationService(db, graph_client=self._graph)
            outcome_counts: Counter = Counter()
            for item in payload.value:
                outcome = await self._process_item(
                    item,
                    subscription_repo,
                    processed_repo,
                    task_service,
                    task_repository,
                    known_users,
                    conversation_service,
                )
                outcome_counts[outcome] += 1

            handled = outcome_counts[MessageOutcome.HANDLED.value]
            logger.info(
                "Webhook notification batch finished: %d item(s) total, handled=%d "
                "already_processed=%d whitelist_skipped=%d rejected=%d",
                len(payload.value),
                handled,
                outcome_counts[MessageOutcome.ALREADY_PROCESSED.value],
                outcome_counts[MessageOutcome.WHITELIST_SKIPPED.value],
                outcome_counts[_REJECTED],
            )
            return handled
        finally:
            db.close()

    async def _process_item(
        self,
        item: WebhookNotificationItem,
        subscription_repo: SubscriptionRepository,
        processed_repo: ProcessedEmailRepository,
        task_service: TaskService,
        task_repository: TaskRepository,
        known_users: list[KnownUser],
        conversation_service: ConversationService,
    ) -> str:
        if item.client_state != settings.webhook_client_state:
            logger.warning("Ignoring notification with invalid clientState")
            return _REJECTED

        subscription = subscription_repo.get_by_id(item.subscription_id)
        if not subscription or not subscription.user or subscription.user.is_deleted:
            logger.warning("Unknown or deleted subscription id: %s", item.subscription_id)
            return _REJECTED

        message_id = self._resolve_message_id(item)
        if not message_id:
            logger.warning(
                "Could not resolve message id from notification for subscription %s",
                item.subscription_id,
            )
            return _REJECTED

        try:
            message = await self._load_whitelisted_message(
                item,
                graph_user_id=subscription.graph_user_id,
                message_id=message_id,
                mailbox_email=subscription.user.email,
            )
            if message is None:
                return MessageOutcome.WHITELIST_SKIPPED.value

            outcome = await self.process_message(
                message,
                user_id=subscription.user_id,
                user_email=subscription.user.email,
                processed_repo=processed_repo,
                task_service=task_service,
                created_via="webhook",
                graph_user_id=subscription.graph_user_id,
                known_users=known_users,
                task_repository=task_repository,
                conversation_service=conversation_service,
            )
            return outcome.value
        except Exception as exc:
            logger.warning(
                "Failed to fetch or parse message %s for user %s: %s",
                message_id,
                subscription.graph_user_id,
                exc,
            )
            return _REJECTED

    async def process_message(
        self,
        message: GraphMessage,
        *,
        user_id: uuid.UUID,
        user_email: str,
        processed_repo: ProcessedEmailRepository,
        task_service: TaskService,
        created_via: str,
        graph_user_id: str | None = None,
        known_users: list[KnownUser] | None = None,
        task_repository: TaskRepository | None = None,
        conversation_service: ConversationService | None = None,
    ) -> MessageOutcome:
        """Shared per-message pipeline used by both real-time webhook delivery and the
        scheduled mailbox sync: dedup, whitelist, parse, analyze, apply. Graph's webhook
        delivery is at-least-once and the scheduled sync can overlap it, so `processed_repo`
        is checked/marked here rather than only in one caller."""
        if processed_repo.is_processed(message.internet_message_id):
            logger.info("Skipping already-processed message %s for %s", message.id, user_email)
            return MessageOutcome.ALREADY_PROCESSED

        if not self._passes_email_whitelist(message):
            logger.info(_WHITELIST_SKIP_MESSAGE, message.id)
            processed_repo.mark_processed(user_id, message.internet_message_id)
            return MessageOutcome.WHITELIST_SKIPPED

        processed_repo.mark_processed(user_id, message.internet_message_id)

        if known_users is None:
            known_users = [
                KnownUser(
                    email=u.email,
                    display_name=u.display_name,
                    coverage_topics=list(u.coverage_topics or []),
                )
                for u in task_service.user_repository.get_all(limit=1000)
            ]
        if task_repository is None:
            task_repository = task_service.repository
        if conversation_service is None:
            conversation_service = ConversationService(
                processed_repo.db, graph_client=self._graph
            )

        parsed = parse_graph_message(message, user_email=user_email, user_id=str(user_id))

        existing_task: Task | None = None
        task_summary: str | None = None
        thread_context: str | None = None
        thread_conversation_ids: list[str] = []

        if parsed.conversation_id:
            existing_task = task_repository.get_by_conversation_id(parsed.conversation_id)
            if existing_task is not None:
                task_summary = existing_task.summary

        if (
            (existing_task is None or existing_task.summary is None)
            and parsed.kind == EmailKind.REPLY
        ):
            try:
                thread = await conversation_service.get_thread_for_message(
                    user_email,
                    message,
                    graph_user_id=graph_user_id,
                )
                thread_context = format_thread_context(thread) or None
                thread_conversation_ids = collect_thread_ids(thread)
            except Exception as exc:
                logger.warning(
                    "Failed to backtrack thread for message %s: %s",
                    message.id,
                    exc,
                )

        if existing_task is None and thread_conversation_ids:
            for conversation_id in thread_conversation_ids:
                existing_task = task_repository.get_by_conversation_id(conversation_id)
                if existing_task is not None:
                    task_summary = existing_task.summary
                    break

        email_input = EmailInput.model_validate(parsed.model_dump())
        # Body/subject/addresses are PII/sensitive content — log shape only, never the content.
        logger.info(
            "Email input: kind=%s subject_len=%d body_len=%d to_count=%d cc_count=%d bcc_count=%d",
            email_input.kind,
            len(email_input.subject or ""),
            len(email_input.body_text or ""),
            len(email_input.to),
            len(email_input.cc),
            len(email_input.bcc),
        )

        analysis = await self._analyzer.analyze(
            email_input,
            known_users=known_users,
            task_summary=task_summary,
            thread_context=thread_context,
                has_existing_task=existing_task is not None,
        )    

        # analysis.payload holds LLM-extracted title/description/assignees — sensitive content
        # derived from the email; log only the decision metadata, never the payload itself.
        logger.info(
            "Email analysis result: action=%s intent=%s confidence=%.2f",
            analysis.action.value,
            analysis.intent.value,
            analysis.confidence,
        )

        task = await task_service.apply_analysis(
            analysis,
            parsed,
            parsed.from_address,
            created_via=created_via,
            existing_task=existing_task,
            thread_conversation_ids=thread_conversation_ids or None,
        )
        if task is not None:
            logger.info("Task %s %s from email %s", task.id, analysis.action.value, message.id)
        else:
            logger.info(
                "Message %s analyzed as %s, no task change", message.id, analysis.action.value
            )
        return MessageOutcome.HANDLED

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
        identity = self._message_from_rich_notification(item)
        if identity is None:
            logger.info(
                "No usable encryptedContent for message %s; Graph GET for whitelist check",
                message_id,
            )
            identity = await self._graph.get_message(graph_user_id, message_id)
            if not self._passes_email_whitelist(identity):
                logger.info(_WHITELIST_SKIP_MESSAGE, message_id)
                return None
            return identity

        if not self._passes_email_whitelist(identity):
            logger.info(_WHITELIST_SKIP_MESSAGE, message_id)
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
