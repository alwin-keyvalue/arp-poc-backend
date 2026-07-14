from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.dependencies import is_duplicate_notification
from app.integrations.microsoft_graph.client import GraphClient
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.processors.logging_processor import LoggingEmailProcessor
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import EmailInput
from app.schemas.subscription import WebhookNotificationPayload
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

        db = SessionLocal()
        try:
            subscription_repo = SubscriptionRepository(db)
            task_service = TaskService(TaskRepository(db), UserRepository(db), get_bot_service())
            processed_count = 0

            for item in payload.value:
                if item.client_state != settings.webhook_client_state:
                    logger.warning("Ignoring notification with invalid clientState")
                    continue

                subscription = subscription_repo.get_by_id(item.subscription_id)
                if not subscription or not subscription.user or subscription.user.is_deleted:
                    logger.warning("Unknown or deleted subscription id: %s", item.subscription_id)
                    continue

                message_id = item.resource.split("/")[-1]
                if is_duplicate_notification(item.subscription_id, message_id):
                    logger.info("Skipped duplicate notification for message %s", message_id)
                    continue

                try:
                    message = await self._graph.get_message(
                        subscription.graph_user_id,
                        message_id,
                    )
                    parsed_email, metadata = parse_graph_message(
                        message,
                        user_email=subscription.user.email,
                        user_id=str(subscription.user_id),
                    )
                    email_input = EmailInput.model_validate(parsed_email.model_dump())
                    if _dev_analyze is not None:
                        analysis = await _dev_analyze(self._analyzer, email_input, metadata)
                    else:
                        analysis = await self._analyzer.analyze(email_input)
                    processed_count += 1
                    logger.info(
                        "Processed message %s for %s (reply=%s, forwarded=%s)",
                        message_id,
                        subscription.user.email,
                        parsed_email.is_reply,
                        parsed_email.is_forwarded,
                    )
                    logger.info(
                        "Email analysis result: %s",
                        analysis.model_dump_json(),
                    )
                    task = await task_service.apply_analysis(
                        analysis,
                        metadata,
                        parsed_email.from_address,
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
