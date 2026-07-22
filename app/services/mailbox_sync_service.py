from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import httpx

from app.database import SessionLocal
from app.integrations.microsoft_graph.client import GraphClient
from app.models.graph_subscription import GraphSubscriptionRecord
from app.repositories.processed_email_repository import ProcessedEmailRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.label_repository import LabelRepository
from app.repositories.task_change_history_repository import TaskChangeHistoryRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import KnownUser
from app.services.bot_service import get_bot_service
from app.services.email_analysis import Analyzer
from app.services.task_service import TaskService
from app.services.webhook_processor_service import MessageOutcome, WebhookProcessorService

logger = logging.getLogger(__name__)

# Bounds how many users' mailboxes are fetched from Graph concurrently, to stay well under
# Graph's per-app throttling limits when the user base is large.
_MAX_CONCURRENT_USERS = 4


class MailboxSyncService:
    def __init__(self, http_client: httpx.AsyncClient, analyzer: Analyzer, *, lookback_days: int):
        self._graph = GraphClient(http_client)
        self._processor = WebhookProcessorService(http_client, analyzer)
        self._lookback_days = lookback_days

    async def sync_all_users(self, user_ids: Optional[Sequence[uuid.UUID]] = None) -> int:
        db = SessionLocal()
        try:
            subscription_repo = SubscriptionRepository(db)
            records = (
                subscription_repo.get_all_by_user_ids(list(user_ids))
                if user_ids is not None
                else subscription_repo.get_all()
            )
            # One subscription record per user is enough to know their graph_user_id;
            # a user can have several (inbox + sentitems), so dedupe by user_id.
            subscriptions_by_user: dict[uuid.UUID, GraphSubscriptionRecord] = {}
            for record in records:
                subscriptions_by_user.setdefault(record.user_id, record)

            # Built once per run and reused for every user/message: KnownUser is a plain
            # Pydantic value with no session dependency, so it's safe to share across the
            # concurrent _sync_user tasks below. Without this, process_message's own
            # known_users fallback would otherwise re-run this same query on every single
            # message processed (N fetches of up to 1000 rows each, for N messages).
            known_users = [
                KnownUser(
                    email=u.email,
                    display_name=u.display_name,
                    coverage_topics=list(u.coverage_topics or []),
                )
                for u in UserRepository(db).get_all(limit=1000)
            ]
        finally:
            db.close()

        if user_ids is not None:
            missing = set(user_ids) - set(subscriptions_by_user)
            if missing:
                logger.warning("No subscribed mailbox found for requested user_ids: %s", missing)

        logger.info(
            "Starting mailbox sync: %d user(s) queued (lookback_days=%d, user_ids filter=%s)",
            len(subscriptions_by_user),
            self._lookback_days,
            list(user_ids) if user_ids is not None else "none (all subscribed users)",
        )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_USERS)

        async def _sync_one(user_id: uuid.UUID, record: GraphSubscriptionRecord) -> None:
            async with semaphore:
                await self._sync_user(user_id, record.graph_user_id, record.user.email, known_users)

        results = await asyncio.gather(
            *(_sync_one(user_id, record) for user_id, record in subscriptions_by_user.items()),
            return_exceptions=True,
        )
        failed = 0
        for user_id, result in zip(subscriptions_by_user, results):
            if isinstance(result, Exception):
                failed += 1
                logger.warning("Mailbox sync failed for user %s: %s", user_id, result)
        logger.info(
            "Finished mailbox sync: %d user(s) attempted, %d failed",
            len(subscriptions_by_user),
            failed,
        )
        return len(subscriptions_by_user)

    async def _sync_user(
        self,
        user_id: uuid.UUID,
        graph_user_id: str,
        user_email: str,
        known_users: list[KnownUser],
    ) -> None:
        since = datetime.now(timezone.utc) - timedelta(days=self._lookback_days)
        messages = await self._graph.list_messages_since(graph_user_id, since)

        db = SessionLocal()
        try:
            processed_repo = ProcessedEmailRepository(db)
            task_service = TaskService(
                TaskRepository(db),
                UserRepository(db),
                get_bot_service(),
                TaskChangeHistoryRepository(db),
                LabelRepository(db),
            )
            outcome_counts: Counter = Counter()
            for message in messages:
                try:
                    outcome = await self._processor.process_message(
                        message,
                        user_id=user_id,
                        user_email=user_email,
                        processed_repo=processed_repo,
                        task_service=task_service,
                        created_via="sync_job",
                        graph_user_id=graph_user_id,
                        known_users=known_users,
                    )
                    outcome_counts[outcome.value] += 1
                except Exception:
                    outcome_counts["failed"] += 1
                    logger.exception(
                        "Failed to process message %s for %s during mailbox sync", message.id, user_email
                    )
            logger.info(
                "Mailbox sync summary for %s: fetched=%d handled=%d already_processed=%d "
                "whitelist_skipped=%d failed=%d",
                user_email,
                len(messages),
                outcome_counts[MessageOutcome.HANDLED.value],
                outcome_counts[MessageOutcome.ALREADY_PROCESSED.value],
                outcome_counts[MessageOutcome.WHITELIST_SKIPPED.value],
                outcome_counts["failed"],
            )
        finally:
            db.close()
