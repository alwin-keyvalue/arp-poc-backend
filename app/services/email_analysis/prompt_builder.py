from app.schemas.email_analysis import LLMEmailContext, IntentType


def _format_email_context(llm_ctx: LLMEmailContext) -> str:
    parts = []
    if llm_ctx.date:
        parts.append(f"Email date: {llm_ctx.date}")
    if llm_ctx.subject:
        parts.append(f"Subject: {llm_ctx.subject}")
    parts.append(f"Is reply: {llm_ctx.is_reply}")
    parts.append(f"Is forwarded: {llm_ctx.is_forwarded}")
    parts.append(f"Current message:\n{llm_ctx.body_text}")
    # if llm_ctx.parent_email_body:
    #     parts.append(f"Parent email content:\n{llm_ctx.parent_email_body}")
    # if llm_ctx.forwarded_email_body:
    #     parts.append(f"Forwarded email content:\n{llm_ctx.forwarded_email_body}")
    return "\n\n".join(parts)


_DUE_DATE_RULES = """## Due Date Rules

Email date is provided for resolving relative deadlines.
- Always output due dates as ISO 8601 datetime with timezone (e.g. 2026-07-10T18:00:00+00:00).
- Resolve relative phrases ("tomorrow", "Friday", "EOD", "by tomorrow evening") using Email date.
- Default times when not specified: morning 09:00, afternoon 14:00, evening 18:00, EOD 17:00.
- Use the same timezone as Email date when possible.
- Search current message for deadlines.
- Return null only when no deadline is stated anywhere."""

_INTENT_CONTEXT_RULES = """## Intent definitions

- "New task": The recipient must do something — respond, share thoughts, review, submit, decide, or complete work. Use this when someone is @mentioned or directly asked a question, even if the email mostly shares background or context.
- "FYI only": Purely informational. No response, review, or deliverable is requested from the recipient.
- "Status update": Updates progress or status on an existing task (not a new request).
- "Date update": Only changes a deadline on an existing task.
- "Reassignment": Reassigns an existing task to someone else.
- "Reminder/follow-up": Nudges about an existing task or pending action.

## New task vs FYI only (important)

Choose "New task" (not "FYI only") when ANY of these apply:
- An @mention is paired with a request or question (e.g. "tell me what you think", "please review", "can you handle this")
- The recipient is asked to respond, opine, review, or take action — even without an explicit deadline
- Forwarded or shared content comes with a ask directed at the recipient

Choose "FYI only" only when the email shares information and explicitly or clearly requires nothing from the recipient.

Examples:
- "@nasser Tell me what you think about this analysis" → New task
- "@bob Please review and share your views on the supply-side implications" → New task
- "Sharing Q3 results for visibility." → FYI only

## Reply context

- A reply that only changes status is a status update, not new task.
- A reply that only changes a deadline is a date update, not new task."""

_SANITIZATION_RULES = """## Data Sanitization Rules

When extracting text fields, remove or generalize confidential, PII, financial, legal, HR, and medical content.
Sanitize: title, summary, reason. Preserve: assignee, watchers, status, priority, all date fields."""

_EXTRACTION_RULES: dict[IntentType, str] = {
    IntentType.NEW_TASK: """## New Task Extraction Rules

- title: short, action-oriented
- summary: exactly two concise sentences
- assignee: from body_text; null if uncertain
- watchers: @mentions only from body_text; exclude assignee
- priority: infer from urgency and wording (P0, P1, P2)
- status: appropriate initial status (draft, to_do, in_progress, blocked_on_hold, done, dropped, rejected_not_a_task)
- due_date: ISO 8601 per due date rules above
- watchers: @mentions in current email content only (not from/to/cc headers).""",

    IntentType.STATUS_UPDATE: """## Status Update Extraction Rules

Extract status and due_date when present.""",

    IntentType.DATE_UPDATE: """## Date Update Extraction Rules

Extract due_date when present.""",

    IntentType.REASSIGNMENT: """## Reassignment Extraction Rules

Extract assignee from the email.""",

    IntentType.REMINDER_FOLLOW_UP: """## Reminder/Follow-up Extraction Rules

Extract reminder_note when the email is a reminder or follow-up.
Do not parse or resolve dates from the message — include any mentioned dates as plain text in reminder_note.""",

}


def intent_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    intent_values = ", ".join(f'"{i.value}"' for i in IntentType)
    system = f"""You are an email intent classifier for a task management system.
Classify the email into exactly one of these intents: {intent_values}.

{_INTENT_CONTEXT_RULES}

Return the intent and a confidence score between 0.0 and 1.0."""
    return system, _format_email_context(llm_ctx)


def extraction_prompt(intent: IntentType, llm_ctx: LLMEmailContext) -> tuple[str, str]:
    due_date_section = ""
    if intent != IntentType.REMINDER_FOLLOW_UP:
        due_date_section = f"\n{_DUE_DATE_RULES}\n"

    system = f"""You are an email task field extractor for a task management system.

The email has been classified as: {intent.value}

Extract structured fields from the email content.
{due_date_section}
{_EXTRACTION_RULES[intent]}

{_SANITIZATION_RULES}"""
    return system, _format_email_context(llm_ctx)
