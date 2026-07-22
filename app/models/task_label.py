import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Uuid
from sqlalchemy.sql import func

from app.database import Base


class TaskLabel(Base):
    __tablename__ = "task_labels"

    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id"), primary_key=True)
    label_id = Column(Uuid(as_uuid=True), ForeignKey("labels.id"), primary_key=True)
    labeled_at = Column(DateTime, server_default=func.now(), nullable=False)
