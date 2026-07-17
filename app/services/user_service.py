import uuid

from fastapi import HTTPException

from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository):
        self._users = repository

    def create_user(self, data: UserCreate) -> UserResponse:
        existing = self._users.get_by_email(data.email, include_deleted=True)
        if existing and not existing.is_deleted:
            raise HTTPException(status_code=409, detail=f"User {data.email} already exists.")
        if existing and existing.is_deleted:
            existing.is_deleted = False
            user = self._users.update(
                existing,
                display_name=data.display_name,
                coverage_topics=data.coverage_topics,
            )
            return UserResponse.model_validate(user)

        user = self._users.create(
            email=data.email,
            display_name=data.display_name,
            coverage_topics=data.coverage_topics,
        )
        return UserResponse.model_validate(user)

    def list_users(self, skip: int = 0, limit: int = 100) -> list[UserResponse]:
        return [UserResponse.model_validate(user) for user in self._users.get_all(skip=skip, limit=limit)]

    def get_user(self, user_id: uuid.UUID) -> UserResponse:
        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return UserResponse.model_validate(user)

    def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> UserResponse:
        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        updated = self._users.update(
            user,
            display_name=data.display_name,
            coverage_topics=data.coverage_topics,
        )
        return UserResponse.model_validate(updated)

    def delete_user(self, user_id: uuid.UUID) -> None:
        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        self._users.soft_delete(user)
