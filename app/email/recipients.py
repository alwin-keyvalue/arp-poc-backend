from __future__ import annotations

import re
from datetime import datetime
from email.utils import format_datetime

from app.graph.models import GraphMessage, Recipient


def extract_addresses(recipients: list[Recipient]) -> list[str]:
    addresses: list[str] = []
    for recipient in recipients:
        address = recipient.email_address.address if recipient.email_address else None
        if address:
            addresses.append(address.strip().lower())
    return addresses


def extract_from_address(message: GraphMessage) -> str | None:
    if not message.from_recipient or not message.from_recipient.email_address:
        return None
    address = message.from_recipient.email_address.address
    return address.strip().lower() if address else None


def format_email_date(sent_date_time: str | None, received_date_time: str | None) -> str | None:
    raw = sent_date_time or received_date_time
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return format_datetime(dt, usegmt=True)
    except ValueError:
        return raw
