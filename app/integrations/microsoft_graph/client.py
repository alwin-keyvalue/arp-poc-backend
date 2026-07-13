from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.microsoft_graph.auth import graph_auth
from app.integrations.microsoft_graph.models import GraphMessage, GraphSubscription, GraphUser

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

MESSAGE_SELECT = (
    "id,subject,from,toRecipients,ccRecipients,bccRecipients,"
    "receivedDateTime,sentDateTime,bodyPreview,body,importance,"
    "isRead,hasAttachments,webLink,conversationId,internetMessageId,"
    "internetMessageHeaders"
)


class GraphClientError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _escape_odata_string(value: str) -> str:
    return value.replace("'", "''")


class GraphClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        token = await graph_auth.get_app_access_token(self._http)
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        request_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            request_headers.update(headers)
        response = await self._http.request(
            method,
            url,
            headers=request_headers,
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
        data = await self._request("GET", f"/users/{quote(email)}")
        return GraphUser.from_graph_response(data)

    async def get_message(self, user_id: str, message_id: str) -> GraphMessage:
        path = f"/users/{user_id}/messages/{message_id}?$select={MESSAGE_SELECT}"
        data = await self._request("GET", path)
        return GraphMessage.from_graph_response(data)

    async def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
        *,
        page_size: int = 50,
        max_messages: int = 200,
    ) -> list[GraphMessage]:
        """Fetch all mailbox messages that share the given conversationId (thread).

        Graph does not allow $filter=conversationId with $orderby; sort locally.
        """
        escaped_id = _escape_odata_string(conversation_id)
        filter_expr = quote(f"conversationId eq '{escaped_id}'", safe="")
        next_url: str | None = (
            f"/users/{user_id}/messages"
            f"?$filter={filter_expr}"
            f"&$top={page_size}"
            f"&$select={MESSAGE_SELECT}"
        )

        messages: list[GraphMessage] = []
        while next_url and len(messages) < max_messages:
            data = await self._request("GET", next_url)
            for item in data.get("value") or []:
                messages.append(GraphMessage.from_graph_response(item))
                if len(messages) >= max_messages:
                    break
            next_url = data.get("@odata.nextLink")

        messages.sort(key=lambda m: m.received_date_time or "")
        return messages

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
