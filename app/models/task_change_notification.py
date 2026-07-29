import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskChangeNotification(Base):
    __tablename__ = "task_change_notifications"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_change_history_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("task_change_history.id", name="fk_task_change_notifications_task_change_history_id"),
        nullable=False,
        index=True,
    )
    # The assignee this notification is for.
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_task_change_notifications_user_id"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
