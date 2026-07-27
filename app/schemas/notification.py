import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel

from app.schemas.task import TaskResponse
from app.schemas.user import UserResponse


class TaskChangeHistoryDetail(BaseModel):
    id: uuid.UUID
    field_name: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source: str
    updated_by: Optional[UserResponse] = None
    processed_email_id: Optional[uuid.UUID] = None
    changed_at: datetime
    task: TaskResponse


class TaskNotificationResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    task_change_history: TaskChangeHistoryDetail


class TaskNotificationPage(BaseModel):
    items: List[TaskNotificationResponse]
    total: int
    page: int
    page_size: int
