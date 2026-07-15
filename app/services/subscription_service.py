from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.microsoft_graph.client import GraphClient, GraphClientError, MESSAGE_SELECT
from app.integrations.microsoft_graph.rich_notifications import (
    RichNotificationError,
    certificate_to_base64,
    public_key_matches_certificate,
)
from app.models.graph_subscription import GraphSubscriptionRecord
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import SubscribedUserResponse

logger = logging.getLogger(__name__)

# Outlook message subscriptions without resource data: up to ~7 days.
# Rich (includeResourceData) Outlook subscriptions: max 1440 minutes (~1 day).
MAX_SUBSCRIPTION_MINUTES_BASIC = 4230
MAX_SUBSCRIPTION_MINUTES_RICH = 1440

# Well-known Graph mail folders we watch. Sent Items covers outbound mail and replies.
WATCHED_MAIL_FOLDERS = ("inbox", "sentitems")

# Outlook rich notifications require $select and forbid Body/UniqueBody.
RICH_MESSAGE_SELECT = ",".join(
    field
    for field in MESSAGE_SELECT.split(",")
    if field.lower() not in {"body"}
)


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

        rich = settings.webhook_include_resource_data
        encryption_certificate: str | None = None
        encryption_certificate_id: str | None = None
        if rich:
            encryption_certificate, encryption_certificate_id = self._require_rich_cert_config()

        graph_user = await self._graph.get_user_by_email(user.email)
        if not user.display_name and graph_user.display_name:
            self._users.update(user, display_name=graph_user.display_name)

        existing = self._subscriptions.get_all_by_user_id(user.id)
        stale = [
            record
            for record in existing
            if not self._resource_matches_notification_mode(record.resource, rich)
        ]
        for record in stale:
            logger.info(
                "Replacing subscription %s for %s — mode mismatch (want rich=%s)",
                record.id,
                user.email,
                rich,
            )
            await self._delete_graph_subscription(record.id, user.email)
            self._subscriptions.delete(record)

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
            resource = self._build_resource(graph_user.id, folder, rich=rich)
            subscription = await self._graph.create_subscription(
                change_type="created",
                notification_url=settings.microsoft_graph_webhook_url,
                resource=resource,
                expiration_date_time=self._get_expiration_datetime(),
                client_state=settings.webhook_client_state,
                include_resource_data=rich,
                encryption_certificate=encryption_certificate,
                encryption_certificate_id=encryption_certificate_id,
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
            logger.info(
                "Created %s subscription %s for %s (rich=%s)",
                folder,
                subscription.id,
                user.email,
                rich,
            )

        return [self._to_response(record) for record in records]

    async def unsubscribe_user(self, email: str) -> dict[str, str]:
        records = self._subscriptions.get_all_by_email(email)
        if not records:
            raise HTTPException(status_code=404, detail=f"No subscription found for {email}.")

        for record in records:
            await self._delete_graph_subscription(record.id, email)

        self._subscriptions.delete_many(records)
        return {"unsubscribed": email}

    def _get_expiration_datetime(self) -> str:
        minutes = (
            MAX_SUBSCRIPTION_MINUTES_RICH
            if settings.webhook_include_resource_data
            else MAX_SUBSCRIPTION_MINUTES_BASIC
        )
        expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
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

    async def _delete_graph_subscription(self, subscription_id: str, email: str) -> None:
        try:
            await self._graph.delete_subscription(subscription_id)
        except GraphClientError as exc:
            # Still remove local rows if Graph already dropped the subscription.
            logger.warning(
                "Failed to delete Graph subscription %s for %s: %s",
                subscription_id,
                email,
                exc,
            )

    @staticmethod
    def _require_rich_cert_config() -> tuple[str, str]:
        cert_id = settings.graph_notification_certificate_id
        cert = settings.graph_notification_certificate
        private_key = settings.graph_notification_private_key
        if not cert_id or not cert or not private_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Rich notifications require GRAPH_NOTIFICATION_CERTIFICATE_ID, "
                    "GRAPH_NOTIFICATION_CERTIFICATE, and GRAPH_NOTIFICATION_PRIVATE_KEY."
                ),
            )
        try:
            certificate_b64 = certificate_to_base64(cert)
        except RichNotificationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not public_key_matches_certificate(cert, private_key):
            raise HTTPException(
                status_code=400,
                detail="GRAPH_NOTIFICATION_PRIVATE_KEY does not match GRAPH_NOTIFICATION_CERTIFICATE.",
            )
        return certificate_b64, cert_id

    @staticmethod
    def _build_resource(graph_user_id: str, folder: str, *, rich: bool) -> str:
        resource = f"/users/{graph_user_id}/mailFolders('{folder}')/messages"
        if rich:
            resource = f"{resource}?$select={RICH_MESSAGE_SELECT}"
        return resource

    @staticmethod
    def _resource_matches_folder(resource: str, folder: str) -> bool:
        needle = f"mailfolders('{folder}')"
        return needle in resource.lower().replace(" ", "")

    @staticmethod
    def _resource_matches_notification_mode(resource: str, rich: bool) -> bool:
        has_select = "$select=" in resource.lower()
        return has_select if rich else not has_select

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
