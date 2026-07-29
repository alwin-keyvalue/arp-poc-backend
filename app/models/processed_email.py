import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.sql import func

from app.database import Base


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_processed_emails_user_id_message_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message_id = Column(String(255), nullable=False)
    processed_at = Column(DateTime, server_default=func.now(), nullable=False)
