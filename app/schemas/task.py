import uuid
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.task import TaskPriority, TaskStatus
from app.schemas.label import LabelResponse
from app.schemas.note import NoteResponse


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    summary: Optional[str] = None
    note: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_ids: List[str] = []
    internet_message_ids: List[str] = []
    # How this task came to exist ("webhook", "scheduled_sync", or None for directly-created
    # tasks) — a fact about its origin, not settable after creation, so this isn't in TaskUpdate.
    created_via: Optional[str] = None
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_ids: List[uuid.UUID] = []
    status: TaskStatus = TaskStatus.TO_DO
    priority: TaskPriority = TaskPriority.P2
    due_date: Optional[date] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    note: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_ids: Optional[List[str]] = None
    internet_message_ids: Optional[List[str]] = None
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_ids: Optional[List[uuid.UUID]] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    labels: List[LabelResponse] = []
    created_at: datetime
    last_update: datetime


class TaskDetailResponse(TaskResponse):
    notes: List[NoteResponse] = []


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    skip: int
    limit: int


class TaskDashboardResponse(BaseModel):
    open_tasks: int
    total: int
    overdue: int
    due_today: int
    due_this_week: int
    completed_pct: int


class UserTaskStatsResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    open_tasks: int
    overdue: int
    due_this_week: int
    completed: int


class TaskChangeHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    field_name: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source: str
    changed_by_oid: Optional[str] = None
    changed_by_name: Optional[str] = None
    processed_email_id: Optional[uuid.UUID] = None
    changed_at: datetime


class TaskActivityPage(BaseModel):
    items: List[TaskChangeHistoryResponse]
    total: int
    page: int
    page_size: int
