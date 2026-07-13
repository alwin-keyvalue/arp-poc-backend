from pydantic import BaseModel, Field

from app.schemas.parsed_email import ParsedEmailInput


class ConversationMessagesResponse(BaseModel):
    """Full mailbox thread: original email + every reply/forward, LLM-ready."""

    conversation_id: str
    user_email: str
    count: int
    original_message: ParsedEmailInput | None = None
    replies: list[ParsedEmailInput] = Field(default_factory=list)
