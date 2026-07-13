import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import relationship

from app.database import Base


class GraphSubscriptionRecord(Base):
    __tablename__ = "graph_subscriptions"

    id = Column(String(255), primary_key=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    graph_user_id = Column(String(255), nullable=False)
    resource = Column(String(512), nullable=False)
    expiration_datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="graph_subscriptions")
