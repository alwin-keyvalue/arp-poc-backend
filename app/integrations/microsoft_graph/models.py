from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailAddress:
    name: str | None = None
    address: str | None = None


@dataclass
class Recipient:
    email_address: EmailAddress | None = None


@dataclass
class MessageBody:
    content_type: str | None = None
    content: str | None = None


@dataclass
class InternetMessageHeader:
    name: str | None = None
    value: str | None = None


@dataclass
class GraphMessage:
    id: str
    subject: str | None = None
    from_recipient: Recipient | None = None
    to_recipients: list[Recipient] = field(default_factory=list)
    cc_recipients: list[Recipient] = field(default_factory=list)
    bcc_recipients: list[Recipient] = field(default_factory=list)
    received_date_time: str | None = None
    sent_date_time: str | None = None
    body_preview: str | None = None
    body: MessageBody | None = None
    importance: str | None = None
    is_read: bool | None = None
    has_attachments: bool | None = None
    web_link: str | None = None
    conversation_id: str | None = None
    internet_message_id: str | None = None
    internet_message_headers: list[InternetMessageHeader] = field(default_factory=list)

    @classmethod
    def from_graph_response(cls, data: dict[str, Any]) -> GraphMessage:
        def parse_recipient(item: dict[str, Any] | None) -> Recipient | None:
            if not item:
                return None
            addr = item.get("emailAddress") or {}
            return Recipient(
                email_address=EmailAddress(
                    name=addr.get("name"),
                    address=addr.get("address"),
                )
            )

        def parse_recipients(items: list[dict[str, Any]] | None) -> list[Recipient]:
            return [parse_recipient(item) for item in (items or []) if item]

        body_data = data.get("body") or {}
        from_data = data.get("from")
        headers = [
            InternetMessageHeader(name=h.get("name"), value=h.get("value"))
            for h in (data.get("internetMessageHeaders") or [])
        ]

        return cls(
            id=data["id"],
            subject=data.get("subject"),
            from_recipient=parse_recipient(from_data),
            to_recipients=parse_recipients(data.get("toRecipients")),
            cc_recipients=parse_recipients(data.get("ccRecipients")),
            bcc_recipients=parse_recipients(data.get("bccRecipients")),
            received_date_time=data.get("receivedDateTime"),
            sent_date_time=data.get("sentDateTime"),
            body_preview=data.get("bodyPreview"),
            body=MessageBody(
                content_type=body_data.get("contentType"),
                content=body_data.get("content"),
            ),
            importance=data.get("importance"),
            is_read=data.get("isRead"),
            has_attachments=data.get("hasAttachments"),
            web_link=data.get("webLink"),
            conversation_id=data.get("conversationId"),
            internet_message_id=data.get("internetMessageId"),
            internet_message_headers=headers,
        )


@dataclass
class GraphSubscription:
    id: str
    resource: str
    expiration_date_time: str
    change_type: str | None = None
    client_state: str | None = None
    notification_url: str | None = None

    @classmethod
    def from_graph_response(cls, data: dict[str, Any]) -> GraphSubscription:
        return cls(
            id=data["id"],
            resource=data.get("resource", ""),
            expiration_date_time=data.get("expirationDateTime", ""),
            change_type=data.get("changeType"),
            client_state=data.get("clientState"),
            notification_url=data.get("notificationUrl"),
        )


@dataclass
class GraphUser:
    id: str
    display_name: str | None = None
    mail: str | None = None
    user_principal_name: str | None = None

    @classmethod
    def from_graph_response(cls, data: dict[str, Any]) -> GraphUser:
        return cls(
            id=data["id"],
            display_name=data.get("displayName"),
            mail=data.get("mail"),
            user_principal_name=data.get("userPrincipalName"),
        )
