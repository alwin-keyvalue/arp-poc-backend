import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskAssignee(Base):
    __tablename__ = "task_assignees"

    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id"), primary_key=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
