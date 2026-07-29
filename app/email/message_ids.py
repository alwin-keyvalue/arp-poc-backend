from __future__ import annotations

import re

from app.integrations.microsoft_graph.models import GraphMessage

_MESSAGE_ID_RE = re.compile(r"<[^<>\s]+>|[A-Za-z0-9._%+\-/=]+@[A-Za-z0-9.\-]+")


def normalize_message_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return normalized
    if not normalized.startswith("<"):
        normalized = f"<{normalized}"
    if not normalized.endswith(">"):
        normalized = f"{normalized}>"
    return normalized


def _extract_message_ids(value: str | None) -> list[str]:
    if not value:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _MESSAGE_ID_RE.finditer(value):
        normalized = normalize_message_id(match.group(0))
        if normalized and normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found


def _header_value(message: GraphMessage, name: str) -> str | None:
    target = name.lower()
    for header in message.internet_message_headers:
        if (header.name or "").lower() == target and header.value:
            return header.value
    return None


def discovery_message_ids(message: GraphMessage) -> set[str]:
    """
    Minimal Message-IDs needed to detect a split Outlook conversation.

    Uses In-Reply-To and the root (leftmost) References id only — not the full
    References chain — to avoid one Graph lookup per historical hop.
    """
    ids: set[str] = set()
    in_reply_to = _extract_message_ids(_header_value(message, "In-Reply-To"))
    if in_reply_to:
        ids.add(in_reply_to[0])

    references = _extract_message_ids(_header_value(message, "References"))
    if references:
        ids.add(references[0])  # root / original
    return ids
