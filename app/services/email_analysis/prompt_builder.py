from app.schemas.email_analysis import LLMEmailContext, IntentType


def _format_email_context(llm_ctx: LLMEmailContext) -> str:
    parts = []
    if llm_ctx.date:
        parts.append(f"Email date: {llm_ctx.date}")
    if llm_ctx.subject:
        parts.append(f"Subject: {llm_ctx.subject}")
    if llm_ctx.from_address:
        parts.append(f"Sender: {llm_ctx.from_address}")
    if llm_ctx.to:
        parts.append("To: " + ", ".join(llm_ctx.to))
    if llm_ctx.cc:
        parts.append("Cc: " + ", ".join(llm_ctx.cc))
    if llm_ctx.bcc:
        parts.append("Bcc: " + ", ".join(llm_ctx.bcc))
    if llm_ctx.known_users:
        known = ", ".join(
            f"{u.display_name} <{u.email}>" if u.display_name else u.email
            for u in llm_ctx.known_users
        )
        parts.append(f"Known users: {known}")
    parts.append(f"Kind: {llm_ctx.kind}")
    if llm_ctx.task_summary:
        parts.append(f"Task history summary (context only):\n{llm_ctx.task_summary}")
    if llm_ctx.thread_context:
        parts.append(f"Thread history (context only):\n{llm_ctx.thread_context}")
    parts.append(f"Current message:\n{llm_ctx.body_text}")
    return "\n\n".join(parts)


_INTENT_RULES = """## Intents
- "New task": recipient must act — review, respond, submit, decide, or complete work.
- "FYI only": informational; no action required from recipient.
- "Task update": changes an existing task — status, deadline, or assignee.
- "Reminder/follow-up": nudge about pending work.

## Decision tree (use Kind from the email context)
- Kind original → "New task" when @mentioned with a request or recipient is asked to act; "FYI only" when nothing is requested.
- Kind reply → prefer "Task update" for deadline changes ("by EOD"), @mention reassignments ("@bob please check this"), or status updates ("Done"). Use "New task" only for a clearly separate new request. Use Task history summary / Thread history when present.
- Kind forwarded → scan the full Current message (including nested quotes/forwards) for actionable @mentions or requests/questions:
  - "New task" only if that ask still looks unresolved (no clear answer, acknowledgment, or close in later nested messages).
  - "FYI only" if there is no ask, or the ask was answered/agreed/closed, or the outer forward is a pure share with nothing open.

Examples:
- "@bob please review" (original) → New task
- "Submit by today EOD" (reply) → Task update
- "Sharing Q3 results" → FYI only
- Forward with "@nasser When do we buy?" then later buy guidance + "Agree" → FYI only
- Forward with "@bob please review the deck" and no later response → New task"""

_FIELD_RULES = """## Rules
- Do not guess or fabricate. If a field cannot be inferred from the provided information, use null (optional fields) or [] (assignees). Title/description must be grounded only in the email content.
- Ignore email signatures. Never use assignees from signature.
- priority (default P2): P0 = urgent/ASAP/immediately/critical; P1 = important/soon/today; P2 = no urgency stated.
- due_date: ISO 8601 date only when clearly stated; resolve relative dates from Email date (morning 09:00, afternoon 14:00, evening 18:00, EOD 17:00); null if none stated in current message. Never put deadlines in title/description.
- title/description: describe the work only (no assignee, no timing).
- summary: one narrative history tree of the thread/task so far for future updates. Write as a short chronological story (not a duplicate of description). Include who asked whom (sender → recipients), assignees, asks/status/deadline/priority changes, and topic. Start from prior Task history summary if present, then fold in the Current message. Do not invent events. Do NOT store PII or confidential data (no phone numbers, addresses, account numbers, personal IDs, passwords, or confidential deal/pricing details). Distinct from description (work to do)."""

_EXTRACTION_RULES: dict[IntentType, str] = {
    IntentType.NEW_TASK: """## Extract
- title: short, action-oriented
- description: work description (imperative), max 2 sentences
- summary: single narrative history tree (prior Task history summary if any + this message; who→whom, assignees, ask/status; no PII/confidential data)
- status: to_do unless clearly otherwise
- assignees: follow Assignee rules below (union mentions + known recipients + coverage)
- Apply rules above.""",

    IntentType.TASK_UPDATE: """## Extract changed fields only (null for unchanged)
- due_date, assignees, status, title, description, priority — only when explicitly changed in the current message.
- summary: always return the updated narrative history tree (prior Task history summary + this message; who→whom, assignees, ask/status; no PII/confidential data).
- When assignees change, apply Assignee rules below.
- Apply all field rules above.""",

    IntentType.REMINDER_FOLLOW_UP: """## Extract
- reminder_note: summarize the nudge; include any dates as plain text (do not resolve them).""",
}

_SANITIZATION_RULES = """## Sanitize title/description for confidential/PII content; preserve status, priority, dates."""

_COVERAGE_MAP = """## Coverage map (topic/region → people)
- Amin, Hamza — US Tech
- Salman, Masira — Non US Tech
- Nasser — China, Commodities, Defence, Industrials, Oil & Gas
- Salman — Technical Analysis
- Hugh, Amin — Global Macro
- Masira, Amin — Global Financials
- Masira, Nasser — Power, Nuclear
- Amin — Crypto
- Masira — All Asia"""

_ASSIGNEE_RULES = f"""## Assignee rules
A task may have multiple assignees. Assignees MUST be users from the Known users list — return their email addresses exactly as listed. Never invent people who are not in Known users.

Build assignees as a UNION of all sources below, then dedupe by email. Drop any mention or coverage name that does not match a Known user (by display name or email). Coverage never removes To/Cc/Bcc known users.

1. Explicit @mentions or tags in the Current message that match a Known user
2. REQUIRED: every To, Cc, or Bcc address that appears in Known users MUST be an assignee (additive — do not drop them when coverage matches)
3. Coverage map (additive): scan Subject + Current message for matching topics/regions (case-insensitive; "oil" matches "Oil & Gas"; "Global Financials" matches Masira, Amin). For every match, ADD the mapped person only if they are in Known users.
   Example: To aleena@... with body "report on Global Financials" and Aleena, Masira, Amin in Known users → aleena@..., masira@..., amin@...
4. If nothing can be matched to Known users, return an empty assignees list

{_COVERAGE_MAP}

## Assignees final check
Every assignees entry must be an email from Known users. Re-check To/Cc/Bcc: any Known user there must appear in assignees. Then add coverage matches. Coverage alone is never enough when Known To/Cc/Bcc recipients exist."""


def intent_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    intent_values = ", ".join(f'"{i.value}"' for i in IntentType)
    system = f"""You are an email intent classifier for a task management system.
Classify into exactly one intent: {intent_values}.

{_INTENT_RULES}

Return intent and confidence (0.0–1.0)."""
    return system, _format_email_context(llm_ctx)


def _include_assignee_rules(intent: IntentType) -> bool:
    return intent in (IntentType.NEW_TASK, IntentType.TASK_UPDATE)


def extraction_prompt(intent: IntentType, llm_ctx: LLMEmailContext) -> tuple[str, str]:
    field_rules = f"\n{_FIELD_RULES}\n" if intent != IntentType.REMINDER_FOLLOW_UP else ""
    assignee_rules = f"\n{_ASSIGNEE_RULES}\n" if _include_assignee_rules(intent) else ""

    system = f"""You are an email task field extractor for a task management system.
Classified intent: {intent.value}

Extract structured fields from the email.
{field_rules}
{_EXTRACTION_RULES[intent]}
{assignee_rules}"""
    return system, _format_email_context(llm_ctx)


def summary_update_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    system = """You maintain a single narrative history tree for a task management system.
Given any prior Task history summary and the Current message, return one updated summary that continues the story.

Write a short chronological narrative useful for future task updates: who said what to whom (sender → To/Cc), assignees involved, asks, status/deadline/priority changes, and topic.
Do not invent events. Do not return a separate history_summary field — only summary.
Do NOT include PII or confidential data (no phone numbers, addresses, account numbers, personal IDs, passwords, or confidential deal/pricing details).
Return only the summary field."""
    return system, _format_email_context(llm_ctx)
