from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SubscribeUserCreate(BaseModel):
    email: EmailStr


class SubscribedUserResponse(BaseModel):
    id: str
    user_email: str
    user_id: str
    display_name: str | None
    resource: str
    expiration_datetime: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookNotificationItem(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    client_state: str = Field(alias="clientState")
    resource: str
    change_type: str = Field(alias="changeType")

    model_config = {"populate_by_name": True}


class WebhookNotificationPayload(BaseModel):
    value: list[WebhookNotificationItem] = Field(default_factory=list)
