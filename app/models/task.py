import enum
import uuid

from sqlalchemy import Column, Date, DateTime, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.task_assignee import TaskAssignee


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
    description = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    source_email_id = Column(String(255), nullable=True)
    source_user = Column(String(255), nullable=True)
    source_link = Column(String(1024), nullable=True)
    # "metadata" is reserved on declarative models (Base.metadata), so the Python attribute
    # is named metadata_ while the actual DB column stays "metadata".
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    labels = Column(JSON, nullable=False, default=list)
    status = Column(String(50), nullable=False, default=TaskStatus.TO_DO.value)
    priority = Column(String(50), nullable=False, default=TaskPriority.P2.value)
    due_date = Column(Date, nullable=True)
    # NULL = not deleted; a timestamp = soft-deleted at that time. Replaces the old plain
    # is_deleted boolean so soft-deletes also record *when*, not just whether.
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_update = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    assignees = relationship("User", secondary=TaskAssignee.__table__, order_by="User.email")

    @property
    def assignee_ids(self) -> list:
        return [user.id for user in self.assignees]

    @property
    def conversation_ids(self) -> list:
        return (self.metadata_ or {}).get("conversation_ids", [])

    @property
    def internet_message_ids(self) -> list:
        return (self.metadata_ or {}).get("internet_message_ids", [])

    @property
    def created_via(self) -> str | None:
        return (self.metadata_ or {}).get("created_via")
