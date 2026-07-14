import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tasks are soft-deleted (see Task.is_deleted), never actually removed, so the row this
    # references always exists — safe to enforce as a real FK.
    task_id = Column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", name="fk_task_status_history_task_id"), nullable=False, index=True
    )
    task_title = Column(String(255), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_by_oid = Column(String(255), nullable=True)
    changed_by_name = Column(String(255), nullable=True)
    source = Column(String(50), nullable=False)
    changed_at = Column(DateTime, server_default=func.now(), nullable=False)
