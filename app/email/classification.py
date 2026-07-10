from __future__ import annotations

import re
from dataclasses import dataclass

from app.email.types import EmailHeader

FORWARD_SUBJECT_RE = re.compile(r"^(fw|fwd|forward)\s*:", re.IGNORECASE)
REPLY_SUBJECT_RE = re.compile(r"^re\s*:", re.IGNORECASE)


@dataclass
class EmailClassification:
    is_reply: bool = False
    is_forwarded: bool = False


def get_header_value(headers: list[EmailHeader], name: str) -> str | None:
    for header in headers:
        if header.name and header.name.lower() == name.lower():
            return header.value.strip() if header.value else None
    return None


def has_thread_headers(headers: list[EmailHeader]) -> bool:
    in_reply_to = get_header_value(headers, "In-Reply-To")
    references = get_header_value(headers, "References")
    return bool(in_reply_to or references)


def has_forward_subject(subject: str | None) -> bool:
    return bool(subject and FORWARD_SUBJECT_RE.match(subject.strip()))


def has_reply_subject(subject: str | None) -> bool:
    return bool(subject and REPLY_SUBJECT_RE.match(subject.strip()))


def has_reply_body_markers(text: str) -> bool:
    lowered = text.lower()
    if "gmail_quote" in lowered:
        return True
    if re.search(r"\bon .+ wrote:\s*$", lowered, re.MULTILINE):
        return True
    if "from:" in lowered and "sent:" in lowered and "subject:" in lowered:
        return True
    return False


def classify_email(
    *,
    subject: str | None,
    headers: list[EmailHeader],
    body_text: str,
) -> EmailClassification:
    if has_forward_subject(subject):
        return EmailClassification(is_reply=False, is_forwarded=True)

    is_reply = (
        has_thread_headers(headers)
        or has_reply_subject(subject)
        or has_reply_body_markers(body_text)
    )
    return EmailClassification(is_reply=is_reply, is_forwarded=False)
