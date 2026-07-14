from __future__ import annotations

from app.schemas.conversation import ConversationMessagesResponse
from app.schemas.parsed_email import ParsedEmailInput

MAX_PRIOR_MESSAGES = 3
MAX_BODY_CHARS = 800


def _truncate_body(text: str, max_chars: int = MAX_BODY_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _format_message(msg: ParsedEmailInput, max_body_chars: int) -> str:
    parts = []
    if msg.date:
        parts.append(msg.date)
    parts.append(f"from={msg.from_address or 'unknown'}")
    parts.append(f"kind={msg.kind.value}")
    return f"[{' | '.join(parts)}]\n{_truncate_body(msg.body_text, max_body_chars)}"


def format_thread_history(
    email: ParsedEmailInput,
    conversation: ConversationMessagesResponse | None,
    max_prior: int = MAX_PRIOR_MESSAGES,
    max_body_chars: int = MAX_BODY_CHARS,
) -> str | None:
    """Build a truncated prior-thread string for the LLM (excludes current email)."""
    if conversation is None:
        return None

    thread = (
        [conversation.original_message] if conversation.original_message else []
    ) + list(conversation.replies)

    priors = [msg for msg in thread if msg.message_id != email.message_id]
    if not priors:
        return None

    root_id = conversation.original_message.message_id if conversation.original_message else None
    root = next((msg for msg in priors if msg.message_id == root_id), None)
    others = [msg for msg in priors if msg.message_id != root_id]
    selected = ([root] if root else []) + others[-max_prior:]

    return "\n\n".join(_format_message(msg, max_body_chars) for msg in selected)
