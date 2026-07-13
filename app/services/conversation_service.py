from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.integrations.microsoft_graph.client import GraphClient, GraphClientError
from app.integrations.microsoft_graph.models import GraphMessage, Recipient
from app.repositories.user_repository import UserRepository
from app.schemas.conversation import ConversationMessageResponse, ConversationMessagesResponse


def _recipient_address(recipient: Recipient) -> str | None:
    if not recipient.email_address or not recipient.email_address.address:
        return None
    return recipient.email_address.address


def _recipient_addresses(recipients: list[Recipient]) -> list[str]:
    return [
        address
        for address in (_recipient_address(recipient) for recipient in recipients)
        if address
    ]


def _to_message_response(message: GraphMessage) -> ConversationMessageResponse:
    from_address = None
    from_name = None
    if message.from_recipient and message.from_recipient.email_address:
        from_address = message.from_recipient.email_address.address
        from_name = message.from_recipient.email_address.name

    return ConversationMessageResponse(
        id=message.id,
        subject=message.subject,
        from_address=from_address,
        from_name=from_name,
        to=_recipient_addresses(message.to_recipients),
        cc=_recipient_addresses(message.cc_recipients),
        bcc=_recipient_addresses(message.bcc_recipients),
        received_date_time=message.received_date_time,
        sent_date_time=message.sent_date_time,
        body_preview=message.body_preview,
        body_content=message.body.content if message.body else None,
        body_content_type=message.body.content_type if message.body else None,
        conversation_id=message.conversation_id,
        internet_message_id=message.internet_message_id,
        web_link=message.web_link,
        has_attachments=message.has_attachments,
        is_read=message.is_read,
    )


def _thread_response(
    *,
    conversation_id: str,
    user_email: str,
    messages: list[GraphMessage],
) -> ConversationMessagesResponse:
    # Oldest message is the original email; the rest are replies/forwards.
    ordered = [_to_message_response(message) for message in messages]
    original = ordered[0] if ordered else None
    replies = ordered[1:] if len(ordered) > 1 else []
    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        user_email=user_email,
        count=len(ordered),
        original_message=original,
        replies=replies,
    )


class ConversationService:
    def __init__(self, db: Session, graph_client: GraphClient):
        self._users = UserRepository(db)
        self._graph = graph_client

    async def get_conversation_messages(
        self,
        email: str,
        conversation_id: str,
    ) -> ConversationMessagesResponse:
        user = self._users.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {email} not found. Create the user first via POST /api/users.",
            )

        try:
            graph_user = await self._graph.get_user_by_email(user.email)
            messages = await self._graph.get_conversation_messages(
                graph_user.id,
                conversation_id,
            )
        except GraphClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return _thread_response(
            conversation_id=conversation_id,
            user_email=user.email,
            messages=messages,
        )


def build_conversation_service(db: Session, http_client: httpx.AsyncClient) -> ConversationService:
    return ConversationService(db, GraphClient(http_client))
