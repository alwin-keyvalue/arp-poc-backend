import uuid

from sqlalchemy import Boolean, Column, DateTime, JSON, String, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    zone = Column(String(64), nullable=True)
    aad_object_id = Column(String(255), nullable=True, index=True)
    teams_conversation_reference = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    graph_subscriptions = relationship(
        "GraphSubscriptionRecord",
        back_populates="user",
        cascade="all, delete-orphan",
    )
