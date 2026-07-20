from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.integrations.microsoft_graph.client import GraphClient, GraphClientError, MESSAGE_SELECT
from app.integrations.microsoft_graph.rich_notifications import (
    RichNotificationError,
    certificate_to_base64,
    public_key_matches_certificate,
)
from app.models.graph_subscription import GraphSubscriptionRecord
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import RenewAllReport, RenewSubscriptionResult, SubscribedUserResponse

logger = logging.getLogger(__name__)

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

        encryption_certificate, encryption_certificate_id = self._require_cert_config()

        graph_user = await self._graph.get_user_by_email(user.email)
        if not user.display_name and graph_user.display_name:
            self._users.update(user, display_name=graph_user.display_name)

        existing = self._subscriptions.get_all_by_user_id(user.id)
        stale = [record for record in existing if not self._is_rich_resource(record.resource)]
        for record in stale:
            logger.info(
                "Replacing non-rich subscription %s for %s",
                record.id,
                user.email,
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
            resource = self._build_resource(graph_user.id, folder)
            subscription = await self._graph.create_subscription(
                change_type="created",
                notification_url=settings.microsoft_graph_webhook_url,
                resource=resource,
                expiration_date_time=self._get_expiration_datetime(),
                client_state=settings.webhook_client_state,
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
            logger.info("Created %s subscription %s for %s", folder, subscription.id, user.email)

        return [self._to_response(record) for record in records]

    async def unsubscribe_user(self, email: str) -> dict[str, str]:
        records = self._subscriptions.get_all_by_email(email)
        if not records:
            raise HTTPException(status_code=404, detail=f"No subscription found for {email}.")

        await self._unsubscribe_records(records, email)
        return {"unsubscribed": email}

    async def unsubscribe_user_if_subscribed(self, email: str) -> None:
        """Like unsubscribe_user, but a no-op rather than a 404 when the user has no
        subscriptions — for cleanup on user deletion, where "nothing to clean up" isn't
        an error. Must be called before the user is soft-deleted: get_all_by_email filters
        out deleted users, so calling this after soft-delete would silently find nothing."""
        records = self._subscriptions.get_all_by_email(email)
        if records:
            await self._unsubscribe_records(records, email)

    async def _unsubscribe_records(
        self, records: list[GraphSubscriptionRecord], email: str
    ) -> None:
        for record in records:
            await self._delete_graph_subscription(record.id, email)
        self._subscriptions.delete_many(records)

    def _get_expiration_datetime(self) -> str:
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=settings.max_subscription_minutes
        )
        return expires.isoformat().replace("+00:00", "Z")

    async def renew_all(self) -> RenewAllReport:
        expiration = self._get_expiration_datetime()
        results: list[RenewSubscriptionResult] = []
        for record in self._subscriptions.get_all():
            results.append(await self._renew_subscription(record, expiration))

        counts = Counter(result.status for result in results)
        return RenewAllReport(
            total=len(results),
            renewed=counts["renewed"],
            recreated=counts["recreated"],
            failed=counts["failed"],
            results=results,
        )

    async def _renew_subscription(
        self,
        record: GraphSubscriptionRecord,
        expiration_date_time: str,
    ) -> RenewSubscriptionResult:
        try:
            renewed = await self._graph.renew_subscription(record.id, expiration_date_time)
            expiration = datetime.fromisoformat(
                renewed.expiration_date_time.replace("Z", "+00:00")
            )
            updated = self._subscriptions.update_expiration(record, expiration)
            return self._renew_result(
                record,
                status="renewed",
                subscription=self._to_response(updated),
            )
        except GraphClientError as exc:
            if exc.status_code == 404:
                return await self._recreate_subscription(record)
            logger.warning(
                "Failed to renew Graph subscription %s for %s: %s",
                record.id,
                record.user.email,
                exc,
            )
            return self._renew_result(record, status="failed", message=str(exc))
        except Exception as exc:
            logger.exception(
                "Unexpected error renewing Graph subscription %s for %s",
                record.id,
                record.user.email,
            )
            return self._renew_result(record, status="failed", message=str(exc))

    async def _recreate_subscription(
        self,
        record: GraphSubscriptionRecord,
    ) -> RenewSubscriptionResult:
        email = record.user.email
        old_id = record.id
        user_id = record.user_id
        graph_user_id = record.graph_user_id
        resource = record.resource

        logger.info(
            "Graph subscription %s for %s not found; recreating same resource",
            old_id,
            email,
        )
        await self._delete_graph_subscription(old_id, email)
        self._subscriptions.delete(record)

        try:
            encryption_certificate, encryption_certificate_id = self._require_cert_config()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return self._renew_result(record, status="failed", message=detail)

        try:
            subscription = await self._graph.create_subscription(
                change_type="created",
                notification_url=settings.microsoft_graph_webhook_url,
                resource=resource,
                expiration_date_time=self._get_expiration_datetime(),
                client_state=settings.webhook_client_state,
                encryption_certificate=encryption_certificate,
                encryption_certificate_id=encryption_certificate_id,
            )
            expiration = datetime.fromisoformat(
                subscription.expiration_date_time.replace("Z", "+00:00")
            )
            created = self._subscriptions.create(
                subscription_id=subscription.id,
                user_id=user_id,
                graph_user_id=graph_user_id,
                resource=subscription.resource,
                expiration_datetime=expiration,
            )
        except GraphClientError as exc:
            logger.warning("Failed to recreate subscription for %s after 404: %s", email, exc)
            return self._renew_result(record, status="failed", message=str(exc))
        except Exception as exc:
            logger.exception("Unexpected error recreating subscription for %s after 404", email)
            return self._renew_result(record, status="failed", message=str(exc))

        return RenewSubscriptionResult(
            user_email=email,
            subscription_id=created.id,
            resource=created.resource,
            status="recreated",
            message=f"Recreated after Graph subscription {old_id} was not found",
            subscription=self._to_response(created),
        )

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
    def _require_cert_config() -> tuple[str, str]:
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
    def _build_resource(graph_user_id: str, folder: str) -> str:
        return (
            f"/users/{graph_user_id}/mailFolders('{folder}')/messages"
            f"?$select={RICH_MESSAGE_SELECT}"
        )

    @staticmethod
    def _resource_matches_folder(resource: str, folder: str) -> bool:
        needle = f"mailfolders('{folder}')"
        return needle in resource.lower().replace(" ", "")

    @staticmethod
    def _is_rich_resource(resource: str) -> bool:
        return "$select=" in resource.lower()

    @staticmethod
    def _renew_result(
        record: GraphSubscriptionRecord,
        *,
        status: str,
        message: str | None = None,
        subscription: SubscribedUserResponse | None = None,
    ) -> RenewSubscriptionResult:
        return RenewSubscriptionResult(
            user_email=record.user.email,
            subscription_id=record.id,
            resource=record.resource,
            status=status,
            message=message,
            subscription=subscription,
        )

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


async def run_renew_all(http_client: httpx.AsyncClient) -> RenewAllReport | None:
    """Background job: opens its own DB session, logs outcome, safe after HTTP 202."""
    db = SessionLocal()
    try:
        service = build_subscription_service(db, http_client)
        report = await service.renew_all()
        _log_renew_report(report)
        return report
    except Exception:
        logger.exception("Subscription renew job failed unexpectedly")
        return None
    finally:
        db.close()


def _log_renew_report(report: RenewAllReport) -> None:
    logger.info(
        "Subscription renew finished: total=%d renewed=%d recreated=%d failed=%d",
        report.total,
        report.renewed,
        report.recreated,
        report.failed,
    )
    for result in report.results:
        if result.status != "failed":
            continue
        logger.warning(
            "Subscription renew failed for %s (%s, %s): %s",
            result.user_email,
            result.subscription_id,
            result.resource,
            result.message,
        )
