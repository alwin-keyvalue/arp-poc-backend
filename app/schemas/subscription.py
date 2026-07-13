from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SubscribeUserCreate(BaseModel):
    email: EmailStr


class SubscribedUserResponse(BaseModel):
    id: str
    user_id: UUID
    user_email: str
    display_name: str | None
    graph_user_id: str
    resource: str
    expiration_datetime: datetime
    created_at: datetime


class WebhookNotificationItem(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    client_state: str = Field(alias="clientState")
    resource: str
    change_type: str = Field(alias="changeType")

    model_config = {"populate_by_name": True}


class WebhookNotificationPayload(BaseModel):
    value: list[WebhookNotificationItem] = Field(default_factory=list)
