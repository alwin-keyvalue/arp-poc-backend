import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str, *, include_deleted: bool = False) -> Optional[User]:
        query = self.db.query(User).filter(User.email == email.lower())
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        return query.first()

    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()

    def get_or_create(
        self,
        *,
        email: str,
        display_name: str | None = None,
    ) -> User:
        normalized_email = email.strip().lower()
        existing = self.get_by_email(normalized_email, include_deleted=True)
        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
            if display_name and existing.display_name != display_name:
                existing.display_name = display_name
            self.db.commit()
            self.db.refresh(existing)
            return existing

        user = User(
            email=normalized_email,
            display_name=display_name,
            is_deleted=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def soft_delete(self, user: User) -> None:
        user.is_deleted = True
        self.db.commit()
        self.db.refresh(user)
