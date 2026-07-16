from __future__ import annotations

from app.schemas.conversation import ConversationMessagesResponse
from app.schemas.parsed_email import ParsedEmailInput

_MAX_BODY_CHARS = 800
_MAX_MESSAGES = 20


def _thread_messages(thread: ConversationMessagesResponse) -> list[ParsedEmailInput]:
    messages: list[ParsedEmailInput] = []
    if thread.original_message is not None:
        messages.append(thread.original_message)
    messages.extend(thread.replies)
    return messages


def _format_one(msg: ParsedEmailInput) -> str:
    bits = []
    if msg.date:
        bits.append(msg.date)
    if msg.from_address:
        bits.append(f"from {msg.from_address}")
    if msg.subject:
        bits.append(f"subject: {msg.subject}")
    header = " | ".join(bits) if bits else "message"
    body = (msg.body_text or "").strip()
    if len(body) > _MAX_BODY_CHARS:
        body = body[:_MAX_BODY_CHARS] + "…"
    return f"- {header}\n{body}" if body else f"- {header}"


def format_thread_context(thread: ConversationMessagesResponse) -> str:
    messages = _thread_messages(thread)
    if not messages:
        return ""
    # Prefer recent context if the thread is long.
    if len(messages) > _MAX_MESSAGES:
        messages = messages[-_MAX_MESSAGES:]
    return "\n\n".join(_format_one(m) for m in messages)


def collect_thread_ids(thread: ConversationMessagesResponse) -> list[str]:
    """Return deduped conversation_ids from the full thread."""
    conversation_ids: list[str] = []
    seen_conv: set[str] = set()

    if thread.conversation_id and thread.conversation_id not in seen_conv:
        seen_conv.add(thread.conversation_id)
        conversation_ids.append(thread.conversation_id)

    for msg in _thread_messages(thread):
        if msg.conversation_id and msg.conversation_id not in seen_conv:
            seen_conv.add(msg.conversation_id)
            conversation_ids.append(msg.conversation_id)

    return conversation_ids
