import uuid
from typing import List

import httpx
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.internal_auth import (
    require_internal_secret_or_teams_user,
    verify_internal_auth_secret,
)
from app.database import get_db
from app.dependencies import get_http_client
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.subscription_service import build_subscription_service
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


def get_user_service(
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> UserService:
    return UserService(UserRepository(db), build_subscription_service(db, http_client))


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_secret_or_teams_user)],
)
def create_user(body: UserCreate, service: UserService = Depends(get_user_service)):
    return service.create_user(body)


@router.get(
    "",
    response_model=List[UserResponse],
    dependencies=[Depends(require_internal_secret_or_teams_user)],
)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    service: UserService = Depends(get_user_service),
):
    return service.list_users(skip=skip, limit=limit)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_internal_secret_or_teams_user)],
)
def get_user(user_id: uuid.UUID, service: UserService = Depends(get_user_service)):
    return service.get_user(user_id)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(verify_internal_auth_secret)],
)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    service: UserService = Depends(get_user_service),
):
    return service.update_user(user_id, body)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_internal_auth_secret)],
)
async def delete_user(user_id: uuid.UUID, service: UserService = Depends(get_user_service)):
    await service.delete_user(user_id)
