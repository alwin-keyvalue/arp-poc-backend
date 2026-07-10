from __future__ import annotations

from app.email.body_splitter import split_email_body
from app.email.classification import classify_email
from app.email.html_to_text import html_to_text
from app.email.recipients import extract_addresses, extract_from_address, format_email_date
from app.graph.models import GraphMessage
from app.schemas.parsed_email import GraphMessageMetadata, ParsedEmailInput


def parse_graph_message(
    message: GraphMessage,
    *,
    user_email: str,
    user_id: str,
) -> tuple[ParsedEmailInput, GraphMessageMetadata]:
    html = message.body.content if message.body and message.body.content_type == "html" else None
    text = message.body.content if message.body and message.body.content_type == "text" else None
    full_text = text or html_to_text(html or "")

    preliminary_classification = classify_email(
        subject=message.subject,
        headers=message.internet_message_headers,
        body_text=full_text,
    )

    split = split_email_body(
        html=html,
        text=text,
        is_reply=preliminary_classification.is_reply,
        is_forwarded=preliminary_classification.is_forwarded,
    )

    classification = classify_email(
        subject=message.subject,
        headers=message.internet_message_headers,
        body_text=split.body_text or full_text,
    )

    parsed = ParsedEmailInput(
        body_text=split.body_text or full_text.strip(),
        date=format_email_date(message.sent_date_time, message.received_date_time),
        is_reply=classification.is_reply,
        is_forwarded=classification.is_forwarded,
        parent_email_body=split.parent_email_body if classification.is_reply else None,
        forwarded_email_body=split.forwarded_email_body if classification.is_forwarded else None,
        subject=message.subject,
        from_address=extract_from_address(message),
        to=extract_addresses(message.to_recipients),
        cc=extract_addresses(message.cc_recipients),
        bcc=extract_addresses(message.bcc_recipients),
    )

    metadata = GraphMessageMetadata(
        message_id=message.id,
        conversation_id=message.conversation_id,
        internet_message_id=message.internet_message_id,
        user_email=user_email,
        user_id=user_id,
        web_link=message.web_link,
    )
    return parsed, metadata
