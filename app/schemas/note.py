import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserResponse


class NoteCreate(BaseModel):
    description: str = Field(min_length=1)


class NoteUpdate(BaseModel):
    description: str = Field(min_length=1)


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    description: str
    created_by: Optional[uuid.UUID] = None
    creator: Optional[UserResponse] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
