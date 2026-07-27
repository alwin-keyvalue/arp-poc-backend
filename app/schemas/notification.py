import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class TaskNotificationResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    task_id: uuid.UUID
    task_title: str
    field_name: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source: str
    changed_at: datetime
    updated_by: Optional[uuid.UUID] = None
    updated_by_name: Optional[str] = None


class TaskNotificationPage(BaseModel):
    items: List[TaskNotificationResponse]
    total: int
    page: int
    page_size: int
