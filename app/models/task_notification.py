import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskNotification(Base):
    __tablename__ = "task_notifications"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True)
    # What happened: "created" or "updated".
    type = Column(String(50), nullable=False)
    # The assignee this notification is for.
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    # "user" -> origin_id is the acting user's users.id; "email" -> origin_id is the
    # processed_emails.id whose analysis triggered the change. No FK constraint on origin_id
    # itself since it references a different table depending on origin_type.
    origin_type = Column(String(20), nullable=False)
    origin_id = Column(Uuid(as_uuid=True), nullable=True)
