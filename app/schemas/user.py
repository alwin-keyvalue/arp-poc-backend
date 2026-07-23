from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str | None = None
    role: str = "user"
    coverage_topics: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    coverage_topics: list[str] | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: str
    coverage_topics: list[str] = Field(default_factory=list)
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}
