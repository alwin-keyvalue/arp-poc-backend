from pydantic import BaseModel, Field


class ConversationMessageResponse(BaseModel):
    id: str
    subject: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    received_date_time: str | None = None
    sent_date_time: str | None = None
    body_preview: str | None = None
    body_content: str | None = None
    body_content_type: str | None = None
    conversation_id: str | None = None
    internet_message_id: str | None = None
    web_link: str | None = None
    has_attachments: bool | None = None
    is_read: bool | None = None


class ConversationMessagesResponse(BaseModel):
    """Full mailbox thread: original email + every reply/forward in that conversation."""

    conversation_id: str
    user_email: str
    count: int
    original_message: ConversationMessageResponse | None = None
    replies: list[ConversationMessageResponse] = Field(default_factory=list)
