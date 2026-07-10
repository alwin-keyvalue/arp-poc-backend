from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.dependencies import is_duplicate_notification
from app.email.parser import parse_graph_message
from app.graph.client import GraphClient
from app.processors.logging_processor import LoggingEmailProcessor
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.subscription import WebhookNotificationPayload

logger = logging.getLogger(__name__)


class WebhookProcessorService:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        email_processor: LoggingEmailProcessor,
    ):
        self._http = http_client
        self._graph = GraphClient(http_client)
        self._email_processor = email_processor

    async def process_notification(self, payload: WebhookNotificationPayload) -> int:
        if not settings.webhook_client_state:
            logger.warning("WEBHOOK_CLIENT_STATE is not configured; ignoring notifications")
            return 0

        db = SessionLocal()
        try:
            subscription_repo = SubscriptionRepository(db)
            processed_count = 0

            for item in payload.value:
                if item.client_state != settings.webhook_client_state:
                    logger.warning("Ignoring notification with invalid clientState")
                    continue

                subscription = subscription_repo.get_by_id(item.subscription_id)
                if not subscription:
                    logger.warning("Unknown subscription id: %s", item.subscription_id)
                    continue

                message_id = item.resource.split("/")[-1]
                if is_duplicate_notification(item.subscription_id, message_id):
                    logger.info("Skipped duplicate notification for message %s", message_id)
                    continue

                try:
                    message = await self._graph.get_message(subscription.user_id, message_id)
                    parsed_email, metadata = parse_graph_message(
                        message,
                        user_email=subscription.user_email,
                        user_id=subscription.user_id,
                    )
                    await self._email_processor.process(parsed_email, metadata=metadata)
                    processed_count += 1
                    logger.info(
                        "Processed message %s for %s (reply=%s, forwarded=%s)",
                        message_id,
                        subscription.user_email,
                        parsed_email.is_reply,
                        parsed_email.is_forwarded,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch or parse message %s for user %s: %s",
                        message_id,
                        subscription.user_id,
                        exc,
                    )

            return processed_count
        finally:
            db.close()
