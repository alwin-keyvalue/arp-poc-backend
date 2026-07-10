from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import httpx

from app.database import get_db
from app.dependencies import get_http_client
from app.schemas.subscription import SubscribeUserCreate, SubscribedUserResponse
from app.services.subscription_service import SubscriptionService, build_subscription_service

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def get_subscription_service(
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> SubscriptionService:
    return build_subscription_service(db, http_client)


@router.get("/users", response_model=list[SubscribedUserResponse])
def list_subscribed_users(service: SubscriptionService = Depends(get_subscription_service)):
    return service.list_subscribed_users()


@router.post("/users", response_model=SubscribedUserResponse)
async def subscribe_user(
    body: SubscribeUserCreate,
    service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.subscribe_user(body.email)


@router.delete("/users/{email}")
def remove_subscribed_user(email: str, service: SubscriptionService = Depends(get_subscription_service)):
    return service.remove_subscribed_user(email)


@router.post("/renew", response_model=list[SubscribedUserResponse])
async def renew_all(service: SubscriptionService = Depends(get_subscription_service)):
    return await service.renew_all()
