import enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.task import TaskCreate, TaskUpdate


# --- Input ---


class EmailInput(BaseModel):
    body_text: str
    date: Optional[str] = None
    is_reply: bool = False
    is_forwarded: bool = False
    # parent_email_body: Optional[str] = None
    # forwarded_email_body: Optional[str] = None
    subject: Optional[str] = None
    from_address: Optional[str] = None
    to: List[str] = []
    cc: List[str] = []
    bcc: List[str] = []


class LLMEmailContext(BaseModel):
    date: Optional[str] = None
    subject: Optional[str] = None
    is_reply: bool = False
    is_forwarded: bool = False
    body_text: str
    # parent_email_body: Optional[str] = None
    # forwarded_email_body: Optional[str] = None


def to_llm_context(email: EmailInput) -> LLMEmailContext:
    return LLMEmailContext(
        date=email.date,
        subject=email.subject,
        is_reply=email.is_reply,
        is_forwarded=email.is_forwarded,
        body_text=email.body_text,
        # parent_email_body=email.parent_email_body,
        # forwarded_email_body=email.forwarded_email_body,
    )


# --- Enums ---


class IntentType(str, enum.Enum):
    NEW_TASK = "New task"
    FYI_ONLY = "FYI only"
    STATUS_UPDATE = "Status update"
    DATE_UPDATE = "Date update"
    REASSIGNMENT = "Reassignment"
    REMINDER_FOLLOW_UP = "Reminder/follow-up"


class ActionType(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    IGNORE = "ignore"
    REMINDER = "reminder"


# --- LLM stage 1 ---


class IntentResponse(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)


# --- LLM stage 2 payloads ---


class ReminderPayload(BaseModel):
    reminder_note: Optional[str] = None


# --- Output ---


class AnalyzeResponse(BaseModel):
    intent: IntentType
    confidence: float
    action: ActionType
    payload: Optional[Union[TaskCreate, TaskUpdate, ReminderPayload]] = None
