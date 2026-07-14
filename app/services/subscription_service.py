from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.microsoft_graph.client import GraphClient, GraphClientError
from app.models.graph_subscription import GraphSubscriptionRecord
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import SubscribedUserResponse

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTION_MINUTES = 4230

# Well-known Graph mail folders we watch. Sent Items covers outbound mail and replies.
WATCHED_MAIL_FOLDERS = ("inbox", "sentitems")


class SubscriptionService:
    def __init__(self, db: Session, graph_client: GraphClient):
        self._users = UserRepository(db)
        self._subscriptions = SubscriptionRepository(db)
        self._graph = graph_client

    def list_subscriptions(self) -> list[SubscribedUserResponse]:
        return [self._to_response(record) for record in self._subscriptions.get_all()]

    async def subscribe_user(self, email: str) -> list[SubscribedUserResponse]:
        user = self._users.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {email} not found. Create the user first via POST /api/users.",
            )

        if not settings.webhook_client_state:
            raise HTTPException(status_code=400, detail="WEBHOOK_CLIENT_STATE is not configured.")
        if not settings.webhook_base_url:
            raise HTTPException(
                status_code=400,
                detail="WEBHOOK_BASE_URL is not configured. Use ngrok for local dev.",
            )

        graph_user = await self._graph.get_user_by_email(user.email)
        if not user.display_name and graph_user.display_name:
            self._users.update(user, display_name=graph_user.display_name)

        existing = self._subscriptions.get_all_by_user_id(user.id)
        covered_folders = {
            folder
            for record in existing
            for folder in WATCHED_MAIL_FOLDERS
            if self._resource_matches_folder(record.resource, folder)
        }
        missing_folders = [f for f in WATCHED_MAIL_FOLDERS if f not in covered_folders]
        if not missing_folders:
            return [self._to_response(record) for record in existing]

        records = list(existing)
        for folder in missing_folders:
            resource = f"/users/{graph_user.id}/mailFolders('{folder}')/messages"
            subscription = await self._graph.create_subscription(
                change_type="created",
                notification_url=settings.microsoft_graph_webhook_url,
                resource=resource,
                expiration_date_time=self._get_expiration_datetime(),
                client_state=settings.webhook_client_state,
            )
            expiration = datetime.fromisoformat(
                subscription.expiration_date_time.replace("Z", "+00:00")
            )
            record = self._subscriptions.create(
                subscription_id=subscription.id,
                user_id=user.id,
                graph_user_id=graph_user.id,
                resource=subscription.resource,
                expiration_datetime=expiration,
            )
            records.append(record)
            logger.info("Created %s subscription %s for %s", folder, subscription.id, user.email)

        return [self._to_response(record) for record in records]

    async def unsubscribe_user(self, email: str) -> dict[str, str]:
        records = self._subscriptions.get_all_by_email(email)
        if not records:
            raise HTTPException(status_code=404, detail=f"No subscription found for {email}.")

        for record in records:
            try:
                await self._graph.delete_subscription(record.id)
            except GraphClientError as exc:
                # Still remove local rows if Graph already dropped the subscription.
                logger.warning(
                    "Failed to delete Graph subscription %s for %s: %s",
                    record.id,
                    email,
                    exc,
                )

        self._subscriptions.delete_many(records)
        return {"unsubscribed": email}

    def _get_expiration_datetime(self) -> str:
        expires = datetime.now(timezone.utc) + timedelta(minutes=MAX_SUBSCRIPTION_MINUTES)
        return expires.isoformat().replace("+00:00", "Z")

    async def renew_all(self) -> list[SubscribedUserResponse]:
        subscriptions = self._subscriptions.get_all()
        expiration_date_time = self._get_expiration_datetime()
        results = []
        for record in subscriptions:
            renewed = await self._graph.renew_subscription(record.id, expiration_date_time)
            expiration = datetime.fromisoformat(
                renewed.expiration_date_time.replace("Z", "+00:00")
            )
            updated = self._subscriptions.update_expiration(record, expiration)
            results.append(self._to_response(updated))
        return results

    @staticmethod
    def _resource_matches_folder(resource: str, folder: str) -> bool:
        needle = f"mailfolders('{folder}')"
        return needle in resource.lower().replace(" ", "")

    @staticmethod
    def _to_response(record: GraphSubscriptionRecord) -> SubscribedUserResponse:
        return SubscribedUserResponse(
            id=record.id,
            user_id=record.user_id,
            user_email=record.user.email,
            display_name=record.user.display_name,
            graph_user_id=record.graph_user_id,
            resource=record.resource,
            expiration_datetime=record.expiration_datetime,
            created_at=record.created_at,
        )


def build_subscription_service(db: Session, http_client: httpx.AsyncClient) -> SubscriptionService:
    return SubscriptionService(db, GraphClient(http_client))
