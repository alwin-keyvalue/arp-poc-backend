from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str | None = None
    zone: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    zone: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    zone: str | None
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}
