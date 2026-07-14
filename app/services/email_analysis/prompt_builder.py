from app.schemas.email_analysis import LLMEmailContext, IntentType


def _format_email_context(llm_ctx: LLMEmailContext) -> str:
    parts = []
    if llm_ctx.date:
        parts.append(f"Email date: {llm_ctx.date}")
    if llm_ctx.subject:
        parts.append(f"Subject: {llm_ctx.subject}")
    if llm_ctx.from_address:
        parts.append(f"Sender: {llm_ctx.from_address}")
    parts.append(f"Is reply: {llm_ctx.is_reply}")
    parts.append(f"Is forwarded: {llm_ctx.is_forwarded}")
    parts.append(f"Current message:\n{llm_ctx.body_text}")
    if llm_ctx.parent_email_body:
        parts.append(f"Parent email content:\n{llm_ctx.parent_email_body}")
    if llm_ctx.forwarded_email_body:
        parts.append(f"Forwarded email content:\n{llm_ctx.forwarded_email_body}")
    return "\n\n".join(parts)


_INTENT_RULES = """## Intents
- "New task": recipient must act — review, respond, submit, decide, or complete work.
- "FYI only": informational; no action required from recipient.
- "Task update": changes an existing task — status, deadline, or assignee.
- "Reminder/follow-up": nudge about pending work.

## Decision tree
If Is reply is true → prefer "Task update" for deadline changes ("by EOD"), @mention reassignments ("@bob please check this"), or status updates ("Done"). Use "New task" only for a clearly separate new request.
If Is reply is false → "New task" when @mentioned with a request or recipient is asked to act; "FYI only" when nothing is requested.

Examples: "@bob please review" → New task | "Submit by today EOD" (reply) → Task update | "Sharing Q3 results" → FYI only"""

_FIELD_RULES = """## Field rules
Signatures: ignore content after "--" (name, title, company). Never use Sender or signature names as assignee.
assignee: @mentioned or directly asked person in message body, without the "@" prefix (e.g. "bob"); null if uncertain.
watchers: other @mentions in body without the "@" prefix; exclude assignee.
priority (default P2): P0 = urgent/ASAP/immediately/critical; P1 = important/soon/this week; P2 = no urgency stated.
due_date: ISO 8601 with timezone; resolve relative dates from Email date (morning 09:00, afternoon 14:00, evening 18:00, EOD 17:00); null if none stated in current message.
Sanitize title/summary for confidential/PII content; preserve assignee, watchers, status, priority, dates."""

_EXTRACTION_RULES: dict[IntentType, str] = {
    IntentType.NEW_TASK: """## Extract
- title: short, action-oriented
- summary: two concise sentences
- status: initial status (to_do unless clearly otherwise)
- Apply all field rules above.""",

    IntentType.TASK_UPDATE: """## Extract changed fields only (null for unchanged)
- due_date, assignee, watchers, status, title, summary, priority — only when explicitly changed in the message.
- Apply all field rules above.""",

    IntentType.REMINDER_FOLLOW_UP: """## Extract
- reminder_note: summarize the nudge; include any dates as plain text (do not resolve them).""",
}


def intent_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    intent_values = ", ".join(f'"{i.value}"' for i in IntentType)
    system = f"""You are an email intent classifier for a task management system.
Classify into exactly one intent: {intent_values}.

{_INTENT_RULES}

Return intent and confidence (0.0–1.0)."""
    return system, _format_email_context(llm_ctx)


def extraction_prompt(intent: IntentType, llm_ctx: LLMEmailContext) -> tuple[str, str]:
    field_rules = f"\n{_FIELD_RULES}\n" if intent != IntentType.REMINDER_FOLLOW_UP else ""

    system = f"""You are an email task field extractor for a task management system.
Classified intent: {intent.value}

Extract structured fields from the email.
{field_rules}
{_EXTRACTION_RULES[intent]}"""
    return system, _format_email_context(llm_ctx)
