from datetime import date
from typing import List

from pydantic import BaseModel, EmailStr, model_validator


class TaskReportRequest(BaseModel):
    from_date: date
    to_date: date
    recipients: List[EmailStr]

    @model_validator(mode="after")
    def check_date_range(self) -> "TaskReportRequest":
        if self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


class TaskReportResponse(BaseModel):
    from_date: date
    to_date: date
    recipients: List[EmailStr]
    task_count: int
