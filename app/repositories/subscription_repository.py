from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.graph_subscription import GraphSubscriptionRecord


class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        subscription_id: str,
        user_id: str,
        user_email: str,
        display_name: str | None,
        resource: str,
        expiration_datetime: datetime,
    ) -> GraphSubscriptionRecord:
        record = GraphSubscriptionRecord(
            id=subscription_id,
            user_id=user_id,
            user_email=user_email,
            display_name=display_name,
            resource=resource,
            expiration_datetime=expiration_datetime,
            created_at=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_expiration(
        self,
        record: GraphSubscriptionRecord,
        expiration_datetime: datetime,
    ) -> GraphSubscriptionRecord:
        record.expiration_datetime = expiration_datetime
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, subscription_id: str) -> Optional[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .filter(GraphSubscriptionRecord.id == subscription_id)
            .first()
        )

    def get_by_email(self, user_email: str) -> Optional[GraphSubscriptionRecord]:
        return (
            self.db.query(GraphSubscriptionRecord)
            .filter(GraphSubscriptionRecord.user_email == user_email)
            .first()
        )

    def get_all(self) -> List[GraphSubscriptionRecord]:
        return self.db.query(GraphSubscriptionRecord).order_by(GraphSubscriptionRecord.created_at).all()

    def delete_by_email(self, user_email: str) -> bool:
        record = self.get_by_email(user_email)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
