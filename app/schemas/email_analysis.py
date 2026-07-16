import enum
from datetime import date
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from app.models.task import TaskPriority, TaskStatus


# --- Input ---

class KnownUser(BaseModel):
    email: str
    display_name: Optional[str] = None


class EmailInput(BaseModel):
    body_text: str
    date: Optional[str] = None
    kind: str
    parent_email_body: Optional[str] = None
    forwarded_email_body: Optional[str] = None
    subject: Optional[str] = None
    from_address: Optional[str] = None
    to: List[str] = []
    cc: List[str] = []
    bcc: List[str] = []


class LLMEmailContext(BaseModel):
    date: Optional[str] = None
    subject: Optional[str] = None
    kind: str
    body_text: str
    from_address: Optional[str] = None
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    bcc: List[str] = Field(default_factory=list)
    known_users: List[KnownUser] = Field(default_factory=list)
    task_summary: Optional[str] = None
    thread_context: Optional[str] = None


def to_llm_context(
    email: EmailInput,
    known_users: List[KnownUser] | None = None,
    task_summary: str | None = None,
    thread_context: str | None = None,
) -> LLMEmailContext:
    return LLMEmailContext(
        date=email.date,
        subject=email.subject,
        kind=email.kind,
        body_text=email.body_text,
        from_address=email.from_address,
        to=list(email.to),
        cc=list(email.cc),
        bcc=list(email.bcc),
        known_users=list(known_users or []),
        task_summary=task_summary,
        thread_context=thread_context,
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
    description: Optional[str] = None
    summary: str = Field(
        description=(
            "Single narrative history tree of the task/thread so far "
            "(who→whom, assignees, asks/status). Updated as new emails arrive."
        ),
    )
    assignees: List[str] = Field(
        default_factory=list,
        description="Emails of Known users only; empty if none match",
    )
    status: TaskStatus = TaskStatus.TO_DO
    priority: TaskPriority = TaskPriority.P2
    due_date: Optional[date] = None


class TaskUpdatePayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = Field(
        default=None,
        description=(
            "Updated narrative history tree incorporating this message "
            "(who→whom, assignees, asks/status)."
        ),
    )
    assignees: Optional[List[str]] = Field(
        default=None,
        description="Emails of Known users only when assignees change; null if unchanged",
    )
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None


class ReminderPayload(BaseModel):
    reminder_note: Optional[str] = None


class SummaryUpdatePayload(BaseModel):
    summary: str = Field(
        description=(
            "Updated narrative history tree incorporating this FYI message "
            "(who→whom, assignees, asks/status)."
        ),
    )


# --- Output ---


class AnalyzeResponse(BaseModel):
    intent: IntentType
    confidence: float
    action: ActionType
    payload: Optional[
        Union[TaskCreatePayload, TaskUpdatePayload, ReminderPayload, SummaryUpdatePayload]
    ] = None
