from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.integrations.microsoft_graph.client import GraphClient, GraphClientError
from app.integrations.microsoft_graph.message_parser import parse_graph_message
from app.integrations.microsoft_graph.models import GraphMessage
from app.repositories.user_repository import UserRepository
from app.schemas.conversation import ConversationMessagesResponse


def _thread_response(
    *,
    user_email: str,
    user_id: str,
    messages: list[GraphMessage],
) -> ConversationMessagesResponse:
    ordered = [
        parse_graph_message(message, user_email=user_email, user_id=user_id)
        for message in messages
    ]
    root = ordered[0] if ordered else None
    return ConversationMessagesResponse(
        conversation_id=(root.conversation_id if root and root.conversation_id else ""),
        user_email=user_email,
        count=len(ordered),
        original_message=root,
        replies=ordered[1:] if len(ordered) > 1 else [],
    )


class ConversationService:
    def __init__(self, db: Session, graph_client: GraphClient):
        self._users = UserRepository(db)
        self._graph = graph_client

    def _require_user(self, email: str):
        user = self._users.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {email} not found. Create the user first via POST /api/users.",
            )
        return user

    async def get_thread_for_message(
        self,
        email: str,
        seed: GraphMessage,
        *,
        graph_user_id: str | None = None,
    ) -> ConversationMessagesResponse:
        """Resolve full related history from a seed Graph message (webhooks)."""
        user = self._require_user(email)
        try:
            user_id = graph_user_id or (await self._graph.get_user_by_email(user.email)).id
            messages = await self._graph.get_related_thread_messages(user_id, seed)
        except GraphClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return _thread_response(
            user_email=user.email,
            user_id=str(user.id),
            messages=messages,
        )

    async def get_conversation_messages(
        self,
        email: str,
        conversation_id: str,
    ) -> ConversationMessagesResponse:
        """
        Start from any Outlook conversationId, then expand only if Message-ID
        links point at a different conversation.
        """
        user = self._require_user(email)

        try:
            graph_user = await self._graph.get_user_by_email(user.email)
            seed_messages = await self._graph.get_conversation_messages(
                graph_user.id,
                conversation_id,
            )
            if not seed_messages:
                return ConversationMessagesResponse(
                    conversation_id=conversation_id,
                    user_email=user.email,
                    count=0,
                    original_message=None,
                    replies=[],
                )
            # Newest message usually has the fullest In-Reply-To / References.
            messages = await self._graph.get_related_thread_messages(
                graph_user.id,
                seed_messages[-1],
                preloaded=seed_messages,
            )
        except GraphClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return _thread_response(
            user_email=user.email,
            user_id=str(user.id),
            messages=messages,
        )


def build_conversation_service(db: Session, http_client: httpx.AsyncClient) -> ConversationService:
    return ConversationService(db, GraphClient(http_client))
