import enum
from datetime import date
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from app.email.thread_history import format_thread_history
from app.models.task import TaskPriority, TaskStatus
from app.schemas.conversation import ConversationMessagesResponse
from app.schemas.parsed_email import ParsedEmailInput


# --- Input ---


class LLMEmailContext(BaseModel):
    date: Optional[str] = None
    subject: Optional[str] = None
    kind: str
    body_text: str
    from_address: Optional[str] = None
    thread_history: Optional[str] = None


def to_llm_context(
    email: ParsedEmailInput,
    conversation: ConversationMessagesResponse | None = None,
) -> LLMEmailContext:
    return LLMEmailContext(
        date=email.date,
        subject=email.subject,
        kind=email.kind.value,
        body_text=email.body_text,
        from_address=email.from_address,
        thread_history=format_thread_history(email, conversation),
    )


# --- Enums ---


class IntentType(str, enum.Enum):
    NEW_TASK = "New task"
    FYI_ONLY = "FYI only"
    TASK_UPDATE = "Task update"
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


class TaskCreatePayload(BaseModel):
    title: str
    summary: Optional[str] = None
    assignee: Optional[str] = None
    watchers: List[str] = []
    status: TaskStatus = TaskStatus.TO_DO
    priority: TaskPriority = TaskPriority.P2
    due_date: Optional[date] = None


class TaskUpdatePayload(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    assignee: Optional[str] = None
    watchers: Optional[List[str]] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None


class ReminderPayload(BaseModel):
    reminder_note: Optional[str] = None


# --- Output ---


class AnalyzeResponse(BaseModel):
    intent: IntentType
    confidence: float
    action: ActionType
    payload: Optional[Union[TaskCreatePayload, TaskUpdatePayload, ReminderPayload]] = None
