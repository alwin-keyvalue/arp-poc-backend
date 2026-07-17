from datetime import datetime
from typing import Literal
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


class RenewSubscriptionResult(BaseModel):
    user_email: str
    subscription_id: str
    resource: str
    status: Literal["renewed", "recreated", "failed"]
    message: str | None = None
    subscription: SubscribedUserResponse | None = None


class RenewAllReport(BaseModel):
    total: int
    renewed: int
    recreated: int
    failed: int
    results: list[RenewSubscriptionResult]


class EncryptedContent(BaseModel):
    data: str
    data_key: str = Field(alias="dataKey")
    data_signature: str = Field(alias="dataSignature")
    encryption_certificate_id: str | None = Field(
        default=None, alias="encryptionCertificateId"
    )
    encryption_certificate_thumbprint: str | None = Field(
        default=None, alias="encryptionCertificateThumbprint"
    )

    model_config = {"populate_by_name": True}


class WebhookResourceData(BaseModel):
    id: str | None = None
    odata_type: str | None = Field(default=None, alias="@odata.type")
    odata_id: str | None = Field(default=None, alias="@odata.id")

    model_config = {"populate_by_name": True, "extra": "allow"}


class WebhookNotificationItem(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    client_state: str | None = Field(default=None, alias="clientState")
    resource: str
    change_type: str = Field(alias="changeType")
    resource_data: WebhookResourceData | None = Field(default=None, alias="resourceData")
    encrypted_content: EncryptedContent | None = Field(
        default=None, alias="encryptedContent"
    )

    model_config = {"populate_by_name": True}


class WebhookNotificationPayload(BaseModel):
    value: list[WebhookNotificationItem] = Field(default_factory=list)
    validation_tokens: list[str] | None = Field(default=None, alias="validationTokens")

    model_config = {"populate_by_name": True}
