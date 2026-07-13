from __future__ import annotations

from app.email.body_splitter import split_email_body
from app.email.classification import classify_email
from app.email.html_to_text import html_to_text
from app.email.recipients import format_email_date, normalize_address
from app.email.types import EmailHeader
from app.integrations.microsoft_graph.models import GraphMessage, Recipient
from app.schemas.parsed_email import ParsedEmailInput


def _extract_addresses(recipients: list[Recipient]) -> list[str]:
    addresses: list[str] = []
    for recipient in recipients:
        if recipient.email_address and recipient.email_address.address:
            normalized = normalize_address(recipient.email_address.address)
            if normalized:
                addresses.append(normalized)
    return addresses


def _extract_from_address(message: GraphMessage) -> str | None:
    if not message.from_recipient or not message.from_recipient.email_address:
        return None
    return normalize_address(message.from_recipient.email_address.address)


def _to_email_headers(message: GraphMessage) -> list[EmailHeader]:
    return [
        EmailHeader(name=header.name, value=header.value)
        for header in message.internet_message_headers
    ]


def parse_graph_message(
    message: GraphMessage,
    *,
    user_email: str,
    user_id: str,
) -> ParsedEmailInput:
    html = message.body.content if message.body and message.body.content_type == "html" else None
    text = message.body.content if message.body and message.body.content_type == "text" else None
    full_text = text or html_to_text(html or "")
    headers = _to_email_headers(message)

    preliminary = classify_email(
        subject=message.subject,
        headers=headers,
        body_text=full_text,
    )

    split = split_email_body(
        html=html,
        text=text,
        is_reply=preliminary.is_reply,
        is_forwarded=preliminary.is_forwarded,
    )

    classification = classify_email(
        subject=message.subject,
        headers=headers,
        body_text=split.body_text or full_text,
    )

    return ParsedEmailInput(
        body_text=split.body_text or full_text.strip(),
        date=format_email_date(message.sent_date_time, message.received_date_time),
        kind=classification.kind,
        parent_email_body=split.parent_email_body if classification.is_reply else None,
        forwarded_email_body=split.forwarded_email_body if classification.is_forwarded else None,
        subject=message.subject,
        from_address=_extract_from_address(message),
        to=_extract_addresses(message.to_recipients),
        cc=_extract_addresses(message.cc_recipients),
        bcc=_extract_addresses(message.bcc_recipients),
        message_id=message.id,
        conversation_id=message.conversation_id,
        internet_message_id=message.internet_message_id,
        user_email=user_email,
        user_id=user_id,
        web_link=message.web_link,
    )
