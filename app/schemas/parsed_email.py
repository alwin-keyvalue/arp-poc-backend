from pydantic import BaseModel, Field

from app.email.classification import EmailKind


class ParsedEmailInput(BaseModel):
    """Flattened LLM-ready email payload (webhook + conversation thread messages)."""

    body_text: str
    date: str | None = None
    kind: EmailKind = EmailKind.ORIGINAL
    parent_email_body: str | None = None
    forwarded_email_body: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    message_id: str
    conversation_id: str | None = None
    internet_message_id: str | None = None
    user_email: str
    user_id: str
    web_link: str | None = None
