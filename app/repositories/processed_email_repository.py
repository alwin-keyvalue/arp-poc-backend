import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.processed_email import ProcessedEmail


class ProcessedEmailRepository:
    def __init__(self, db: Session):
        self.db = db

    def is_processed(self, user_id: uuid.UUID, message_id: str) -> bool:
        return (
            self.db.query(ProcessedEmail.id)
            .filter(ProcessedEmail.user_id == user_id, ProcessedEmail.message_id == message_id)
            .first()
            is not None
        )

    def mark_processed(self, user_id: uuid.UUID, message_id: str) -> None:
        self.db.add(ProcessedEmail(user_id=user_id, message_id=message_id))
        try:
            self.db.commit()
        except IntegrityError:
            # Webhook delivery and a scheduled sync can race on the same message;
            # the unique constraint is the source of truth, this is just a no-op retry.
            self.db.rollback()
