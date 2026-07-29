import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TaskNote(Base):
    __tablename__ = "task_notes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    creator = relationship("User")
