import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LabelBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class LabelCreate(LabelBase):
    pass


class LabelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)


class LabelResponse(LabelBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
