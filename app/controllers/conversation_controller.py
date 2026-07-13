from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import httpx

from app.database import get_db
from app.dependencies import get_http_client
from app.schemas.conversation import ConversationMessagesResponse
from app.services.conversation_service import ConversationService, build_conversation_service

router = APIRouter(
    prefix="/api/microsoft-graph",
    tags=["microsoft-graph"],
)


def get_conversation_service(
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> ConversationService:
    return build_conversation_service(db, http_client)


@router.get(
    "/mailboxes/{email}/conversations/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def get_conversation_messages(
    email: str,
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
):
    """
    Given any message's conversationId (e.g. from a new reply), return the full
    thread: original email first, then every reply/forward in that mailbox.
    """
    return await service.get_conversation_messages(email, conversation_id)
