from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime


def normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    return address.strip().lower()


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
