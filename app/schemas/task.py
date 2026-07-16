import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.task import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    summary: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_ids: List[str] = []
    internet_message_ids: List[str] = []
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_ids: List[uuid.UUID] = []
    labels: List[str] = []
    status: TaskStatus = TaskStatus.TO_DO
    priority: TaskPriority = TaskPriority.P2
    due_date: Optional[date] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    source_email_id: Optional[str] = None
    conversation_ids: Optional[List[str]] = None
    internet_message_ids: Optional[List[str]] = None
    source_user: Optional[str] = None
    source_link: Optional[str] = None
    assignee_ids: Optional[List[uuid.UUID]] = None
    labels: Optional[List[str]] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_update: datetime


class TaskStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    from_status: Optional[str] = None
    to_status: str
    source: str
    changed_by_oid: Optional[str] = None
    changed_by_name: Optional[str] = None
    changed_at: datetime
