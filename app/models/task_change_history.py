import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class TaskChangeHistory(Base):
    __tablename__ = "task_change_history"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tasks are soft-deleted (see Task.deleted_at), never actually removed, so the row this
    # references always exists — safe to enforce as a real FK.
    task_id = Column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", name="fk_task_change_history_task_id"), nullable=False, index=True
    )
    task_title = Column(String(255), nullable=False)
    # Which Task field this row records a change to (e.g. "status", "priority", "assignee_ids").
    field_name = Column(String(50), nullable=False)
    # JSONB rather than String: different fields have different shapes (status/priority/title
    # are plain strings, labels/assignee_ids are lists, due_date is an ISO date or null).
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    changed_by_oid = Column(String(255), nullable=True)
    changed_by_name = Column(String(255), nullable=True)
    source = Column(String(50), nullable=False)
    # Set only when source == "email_analysis" — the inbound email whose analysis produced
    # this change. Changes made through direct API calls (source == "api") leave this null.
    processed_email_id = Column(Uuid(as_uuid=True), ForeignKey("processed_emails.id"), nullable=True)
    changed_at = Column(DateTime, server_default=func.now(), nullable=False)
