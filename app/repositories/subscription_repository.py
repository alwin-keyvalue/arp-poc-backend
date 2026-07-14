import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.graph_subscription import GraphSubscriptionRecord
from app.models.user import User


class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        subscription_id: str,
        user_id: uuid.UUID,
        graph_user_id: str,
        resource: str,
        expiration_datetime: datetime,
    ) -> GraphSubscriptionRecord:
        record = GraphSubscriptionRecord(
            id=subscription_id,
            user_id=user_id,
            graph_user_id=graph_user_id,
            resource=resource,
            expiration_datetime=expiration_datetime,
            created_at=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self.get_by_id(record.id)

    def update_expiration(
        self,
        record: GraphSubscriptionRecord,
        expiration_datetime: datetime,
    ) -> GraphSubscriptionRecord:
        record.expiration_datetime = expiration_datetime
        self.db.commit()
        self.db.refresh(record)
        return self.get_by_id(record.id)

    def get_by_id(self, subscription_id: str) -> Optional[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .options(joinedload(GraphSubscriptionRecord.user))
            .filter(GraphSubscriptionRecord.id == subscription_id)
            .first()
        )

    def get_all_by_user_id(self, user_id: uuid.UUID) -> List[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .options(joinedload(GraphSubscriptionRecord.user))
            .filter(GraphSubscriptionRecord.user_id == user_id)
            .order_by(GraphSubscriptionRecord.created_at)
            .all()
        )

    def get_all_by_email(self, email: str) -> List[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .options(joinedload(GraphSubscriptionRecord.user))
            .join(User)
            .filter(User.email == email.lower(), User.is_deleted.is_(False))
            .order_by(GraphSubscriptionRecord.created_at)
            .all()
        )

    def get_all(self) -> List[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .options(joinedload(GraphSubscriptionRecord.user))
            .join(User)
            .filter(User.is_deleted.is_(False))
            .order_by(GraphSubscriptionRecord.created_at)
            .all()
        )

    def delete(self, record: GraphSubscriptionRecord) -> None:
        self.db.delete(record)
        self.db.commit()

    def delete_many(self, records: List[GraphSubscriptionRecord]) -> None:
        for record in records:
            self.db.delete(record)
        self.db.commit()
