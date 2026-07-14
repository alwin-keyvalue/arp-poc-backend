from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.integrations.microsoft_graph.client import GraphClient
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import WebhookNotificationPayload
from app.services.bot_service import get_bot_service
from app.services.email_analysis import Analyzer
from app.services.task_service import TaskService
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


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
            conversation_service = ConversationService(db, graph_client=self._graph)
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

                message_id = item.resource.split("/")[-1]
                try:
                    message = await self._graph.get_message(
                        subscription.graph_user_id,
                        message_id,
                    )
                    parsed = parse_graph_message(
                        message,
                        user_email=subscription.user.email,
                        user_id=str(subscription.user_id),
                    )
                    conversation = await conversation_service.get_thread_for_message(
                        subscription.user.email,
                        message,
                        graph_user_id=subscription.graph_user_id,
                    )
                    analysis = await self._analyzer.analyze(parsed, conversation)

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
