import uuid
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.processed_email import ProcessedEmail


class ProcessedEmailRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_stats_by_user(self, user_id: uuid.UUID) -> Tuple[int, Optional[datetime]]:
        """Returns (total processed, timestamp of the most recently processed email)."""
        total, last_processed_at = (
            self.db.query(func.count(ProcessedEmail.id), func.max(ProcessedEmail.processed_at))
            .filter(ProcessedEmail.user_id == user_id)
            .one()
        )
        return int(total or 0), last_processed_at

    def is_processed(self, internet_message_id: str) -> bool:
        return (
            self.db.query(ProcessedEmail.id)
            .filter(ProcessedEmail.message_id == internet_message_id)
            .first()
            is not None
        )

    def mark_processed(self, user_id: uuid.UUID, internet_message_id: str) -> uuid.UUID:
        """Returns the id of the (now guaranteed-persisted) row for this (user_id,
        internet_message_id) pair — this call's own insert if it won, otherwise the row
        from whichever concurrent caller won the race (see the IntegrityError comment below)."""
        entry = ProcessedEmail(user_id=user_id, message_id=internet_message_id)
        self.db.add(entry)
        try:
            self.db.commit()
            return entry.id
        except IntegrityError:
            # Webhook delivery and a scheduled sync can race on the same message; the unique
            # constraint is the source of truth, so this call's own row (entry.id, generated
            # client-side and never actually persisted) isn't valid — look up the row that
            # actually won instead.
            self.db.rollback()
            existing = (
                self.db.query(ProcessedEmail)
                .filter(ProcessedEmail.user_id == user_id, ProcessedEmail.message_id == internet_message_id)
                .one()
            )
            return existing.id
