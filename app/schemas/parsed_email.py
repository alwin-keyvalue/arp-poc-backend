from pydantic import BaseModel, Field


class ParsedEmailInput(BaseModel):
    body_text: str
    date: str | None
    is_reply: bool = False
    is_forwarded: bool = False
    parent_email_body: str | None = None
    forwarded_email_body: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)


class GraphMessageMetadata(BaseModel):
    message_id: str
    conversation_id: str | None = None
    internet_message_id: str | None = None
    user_email: str
    user_id: str
    web_link: str | None = None
