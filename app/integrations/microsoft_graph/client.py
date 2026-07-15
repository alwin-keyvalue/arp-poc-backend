from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.email.message_ids import discovery_message_ids, normalize_message_id
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
        if response.status_code in (202, 204):
            return None
        return response.json()

    async def get_user_by_email(self, email: str) -> GraphUser:
        data = await self._request("GET", f"/users/{quote(email)}")
        return GraphUser.from_graph_response(data)

    async def get_message(self, user_id: str, message_id: str) -> GraphMessage:
        path = f"/users/{user_id}/messages/{message_id}?$select={MESSAGE_SELECT}"
        data = await self._request("GET", path)
        return GraphMessage.from_graph_response(data)

    async def get_message_by_internet_message_id(
        self,
        user_id: str,
        internet_message_id: str,
    ) -> GraphMessage | None:
        # Graph stores Message-IDs with angle brackets; one lookup is enough.
        candidate = normalize_message_id(internet_message_id)
        escaped = _escape_odata_string(candidate)
        filter_expr = quote(f"internetMessageId eq '{escaped}'", safe="")
        path = (
            f"/users/{user_id}/messages"
            f"?$filter={filter_expr}"
            f"&$top=1"
            f"&$select={MESSAGE_SELECT}"
        )
        data = await self._request("GET", path)
        values = data.get("value") or []
        if values:
            return GraphMessage.from_graph_response(values[0])
        return None

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

    async def get_related_thread_messages(
        self,
        user_id: str,
        seed: GraphMessage,
        *,
        max_messages: int = 200,
        preloaded: list[GraphMessage] | None = None,
    ) -> list[GraphMessage]:
        """
        Load related history with few Graph calls.

        1) Fetch seed conversationId first (covers same-conversation replies/fwds).
        2) Only look up In-Reply-To / root References Message-IDs that are missing
           from that conversation — to catch Outlook split-conversation cases.
        3) Fetch any newly discovered conversationIds once.
        """
        by_graph_id: dict[str, GraphMessage] = {seed.id: seed}
        for message in preloaded or []:
            by_graph_id[message.id] = message

        conversation_ids: set[str] = set()
        if seed.conversation_id:
            conversation_ids.add(seed.conversation_id)
        for message in by_graph_id.values():
            if message.conversation_id:
                conversation_ids.add(message.conversation_id)

        fetched_conversation_ids: set[str] = set()
        if preloaded is not None and seed.conversation_id:
            # Caller already loaded this conversation.
            fetched_conversation_ids.add(seed.conversation_id)

        async def _fetch_pending_conversations() -> None:
            for conversation_id in list(conversation_ids - fetched_conversation_ids):
                fetched_conversation_ids.add(conversation_id)
                for message in await self.get_conversation_messages(
                    user_id,
                    conversation_id,
                    max_messages=max_messages,
                ):
                    by_graph_id[message.id] = message
                    if message.conversation_id:
                        conversation_ids.add(message.conversation_id)

        await _fetch_pending_conversations()

        known_internet_ids = {
            normalize_message_id(message.internet_message_id)
            for message in by_graph_id.values()
            if message.internet_message_id
        }

        # Prefer headers from the newest message — usually the richest References.
        newest = max(
            by_graph_id.values(),
            key=lambda m: m.received_date_time or m.sent_date_time or "",
        )
        for message_id in discovery_message_ids(newest) | discovery_message_ids(seed):
            if message_id in known_internet_ids:
                continue
            found = await self.get_message_by_internet_message_id(user_id, message_id)
            if not found:
                continue
            by_graph_id[found.id] = found
            if found.internet_message_id:
                known_internet_ids.add(normalize_message_id(found.internet_message_id))
            if found.conversation_id:
                conversation_ids.add(found.conversation_id)

        await _fetch_pending_conversations()

        messages = list(by_graph_id.values())
        messages.sort(key=lambda m: m.received_date_time or m.sent_date_time or "")
        return messages[:max_messages]

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

    async def delete_subscription(self, subscription_id: str) -> None:
        await self._request("DELETE", f"/subscriptions/{subscription_id}")

    async def send_mail(
        self,
        *,
        from_user_id: str,
        to_recipients: list[str],
        subject: str,
        html_body: str,
    ) -> None:
        await self._request(
            "POST",
            f"/users/{quote(from_user_id)}/sendMail",
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": html_body},
                    "toRecipients": [{"emailAddress": {"address": address}} for address in to_recipients],
                },
                "saveToSentItems": "false",
            },
        )
