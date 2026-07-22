import uuid

from sqlalchemy import Column, DateTime, String, Uuid
from sqlalchemy.sql import func

from app.database import Base


class Label(Base):
    __tablename__ = "labels"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
