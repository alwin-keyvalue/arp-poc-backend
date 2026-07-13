import enum
import uuid

from sqlalchemy import Column, Date, DateTime, JSON, String, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskStatus(str, enum.Enum):
    # DRAFT = "draft"
    TO_DO = "to_do"
    # IN_PROGRESS = "in_progress"
    # BLOCKED_ON_HOLD = "blocked_on_hold"
    DONE = "done"
    DROPPED = "dropped"
    # REJECTED_NOT_A_TASK = "rejected_not_a_task"


class TaskPriority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    source_email_id = Column(String(255), nullable=True)
    conversation_id = Column(String(255), nullable=True)
    source_user = Column(String(255), nullable=True)
    source_link = Column(String(1024), nullable=True)
    assignee = Column(String(255), nullable=True)
    watchers = Column(JSON, nullable=False, default=list)
    labels = Column(JSON, nullable=False, default=list)
    status = Column(String(50), nullable=False, default=TaskStatus.TO_DO.value)
    priority = Column(String(50), nullable=False, default=TaskPriority.P2.value)
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_update = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
