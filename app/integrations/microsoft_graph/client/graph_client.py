from __future__ import annotations

from typing import Any

import httpx

from app.integrations.microsoft_graph.client.auth import graph_auth
from app.integrations.microsoft_graph.client.models import (
    GraphMessage,
    GraphSubscription,
    GraphUser,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

MESSAGE_SELECT = (
    "subject,from,toRecipients,ccRecipients,bccRecipients,"
    "receivedDateTime,sentDateTime,bodyPreview,body,importance,"
    "isRead,hasAttachments,webLink,conversationId,internetMessageId,"
    "internetMessageHeaders"
)


class GraphClientError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class GraphClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        token = await graph_auth.get_app_access_token(self._http)
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        response = await self._http.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=json,
        )
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise GraphClientError(detail, response.status_code)
        if response.status_code == 204:
            return None
        return response.json()

    async def get_user_by_email(self, email: str) -> GraphUser:
        data = await self._request("GET", f"/users/{email}")
        return GraphUser.from_graph_response(data)

    async def get_message(self, user_id: str, message_id: str) -> GraphMessage:
        path = f"/users/{user_id}/messages/{message_id}?$select={MESSAGE_SELECT}"
        data = await self._request("GET", path)
        return GraphMessage.from_graph_response(data)

    async def create_subscription(
        self,
        *,
        change_type: str,
        notification_url: str,
        resource: str,
        expiration_date_time: str,
        client_state: str,
    ) -> GraphSubscription:
        data = await self._request(
            "POST",
            "/subscriptions",
            json={
                "changeType": change_type,
                "notificationUrl": notification_url,
                "resource": resource,
                "expirationDateTime": expiration_date_time,
                "clientState": client_state,
            },
        )
        return GraphSubscription.from_graph_response(data)

    async def renew_subscription(
        self,
        subscription_id: str,
        expiration_date_time: str,
    ) -> GraphSubscription:
        data = await self._request(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            json={"expirationDateTime": expiration_date_time},
        )
        return GraphSubscription.from_graph_response(data)
