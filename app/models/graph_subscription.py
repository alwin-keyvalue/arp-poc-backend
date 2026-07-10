from sqlalchemy import Column, DateTime, String

from app.database import Base


class GraphSubscriptionRecord(Base):
    __tablename__ = "graph_subscriptions"

    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False)
    user_email = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    resource = Column(String(512), nullable=False)
    expiration_datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
