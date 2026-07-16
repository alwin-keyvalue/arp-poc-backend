import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        email: str,
        display_name: str | None = None,
        zone: str | None = None,
    ) -> User:
        user = User(
            email=email.strip().lower(),
            display_name=display_name,
            zone=zone,
            is_deleted=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_email(self, email: str, *, include_deleted: bool = False) -> Optional[User]:
        query = self.db.query(User).filter(User.email == email.strip().lower())
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        return query.first()

    def get_by_id(self, user_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[User]:
        query = self.db.query(User).filter(User.id == user_id)
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        return query.first()

    def find_by_name_or_email(self, value: str, *, include_deleted: bool = False) -> Optional[User]:
        if not value or not value.strip():
            return None
        needle = value.strip()
        if "@" in needle:
            return self.get_by_email(needle, include_deleted=include_deleted)

        lowered = needle.lower()
        query = self.db.query(User).filter(User.display_name.isnot(None))
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        user = query.filter(func.lower(User.display_name) == lowered).first()
        if user:
            return user
        return (
            query.filter(func.lower(User.display_name).like(f"{lowered} %")).first()
        )

    def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        return (
            self.db.query(User)
            .filter(User.is_deleted.is_(False))
            .order_by(User.created_at)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, user: User, *, display_name: str | None = None, zone: str | None = None) -> User:
        if display_name is not None:
            user.display_name = display_name
        if zone is not None:
            user.zone = zone
        self.db.commit()
        self.db.refresh(user)
        return user

    def soft_delete(self, user: User) -> None:
        user.is_deleted = True
        self.db.commit()
        self.db.refresh(user)

    def upsert_teams_info(
        self,
        *,
        email: str,
        aad_object_id: str,
        conversation_reference: Dict[str, Any],
        display_name: str | None = None,
    ) -> User:
        user = self.get_by_email(email, include_deleted=True)
        if user:
            user.aad_object_id = aad_object_id
            user.teams_conversation_reference = conversation_reference
            if display_name and not user.display_name:
                user.display_name = display_name
            if user.is_deleted:
                user.is_deleted = False
            self.db.commit()
            self.db.refresh(user)
            return user

        user = User(
            email=email.strip().lower(),
            display_name=display_name,
            aad_object_id=aad_object_id,
            teams_conversation_reference=conversation_reference,
            is_deleted=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
