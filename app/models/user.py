import uuid

from sqlalchemy import ARRAY, Boolean, Column, DateTime, JSON, String, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Placeholder actor for task_change_history.updated_by on automatic changes (email/webhook
# -triggered) that have no real acting user. Seeded by the
# 8f1c2a9d4b6e_seed_system_user migration.
SYSTEM_USER_ID = uuid.UUID(int=0)


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="user", server_default="user")
    coverage_topics = Column(ARRAY(String), nullable=False, default=list, server_default="{}")
    aad_object_id = Column(String(255), nullable=True, index=True)
    teams_conversation_reference = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    graph_subscriptions = relationship(
        "GraphSubscriptionRecord",
        back_populates="user",
        cascade="all, delete-orphan",
    )
