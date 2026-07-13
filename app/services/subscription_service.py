from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.microsoft_graph.client import GraphClient
from app.models.graph_subscription import GraphSubscriptionRecord
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import SubscribedUserResponse

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTION_MINUTES = 4230


class SubscriptionService:
    def __init__(self, db: Session, graph_client: GraphClient):
        self._users = UserRepository(db)
        self._subscriptions = SubscriptionRepository(db)
        self._graph = graph_client

    def list_subscribed_users(self) -> list[SubscribedUserResponse]:
        return [self._to_response(record) for record in self._subscriptions.get_all()]

    async def subscribe_user(self, email: str) -> SubscribedUserResponse:
        existing = self._subscriptions.get_by_email(email)
        if existing:
            return self._to_response(existing)

        if not settings.webhook_client_state:
            raise HTTPException(status_code=400, detail="WEBHOOK_CLIENT_STATE is not configured.")
        if not settings.webhook_base_url:
            raise HTTPException(
                status_code=400,
                detail="WEBHOOK_BASE_URL is not configured. Use ngrok for local dev.",
            )

        graph_user = await self._graph.get_user_by_email(email)
        resolved_email = graph_user.mail or graph_user.user_principal_name or email

        user = self._users.get_or_create(
            email=resolved_email,
            display_name=graph_user.display_name,
        )

        existing = self._subscriptions.get_by_user_id(user.id)
        if existing:
            return self._to_response(existing)

        subscription = await self._graph.create_subscription(
            change_type="created",
            notification_url=settings.microsoft_graph_webhook_url,
            resource=f"/users/{graph_user.id}/mailFolders('inbox')/messages",
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
        return self._to_response(record)

    def remove_subscribed_user(self, email: str) -> dict[str, str]:
        record = self._subscriptions.get_by_email(email)
        if not record:
            raise HTTPException(status_code=404, detail=f"User {email} is not subscribed.")
        self._subscriptions.delete(record)
        return {"removed": email}

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
