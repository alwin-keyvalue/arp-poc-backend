import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.task import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str
    summary: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_id: Optional[str] = None
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    watchers: List[str] = []
    labels: List[str] = []
    status: TaskStatus = TaskStatus.DRAFT
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[date] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_id: Optional[str] = None
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    watchers: Optional[List[str]] = None
    labels: Optional[List[str]] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_update: datetime
