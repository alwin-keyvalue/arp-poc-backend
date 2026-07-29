from app.schemas.email_analysis import LLMEmailContext, KnownUser


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}"


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
        parts.append(f"Task history summary:\n{llm_ctx.task_summary}")
    if llm_ctx.thread_context:
        parts.append(f"Thread history:\n{llm_ctx.thread_context}")
    parts.append(f"Current message:\n{llm_ctx.body_text}")
    return _section("Email context", "\n\n".join(parts))


_FIELD_RULES = """Do not guess or fabricate. Use null (optional fields) or [] (assignees) when unknown.
Ignore email signatures.
priority: P0 = urgent/ASAP/critical; P1 = important/soon/today/tomorrow; P2 = default or deadlines further out. Keep priority aligned with due_date and urgency wording.
due_date: ISO 8601 date when clearly stated; resolve relative dates from Email date (morning 09:00, afternoon 14:00, evening 18:00, EOD 17:00); null otherwise. Never put deadlines in title/description.
title/description: describe the work only (no assignee, no timing).
summary: short chronological narrative (who→whom, assignees, asks, status/deadline/priority changes). Extend prior Task history summary if present. Not a duplicate of description."""

_SANITIZATION_RULES = """Apply to title, description, and summary before returning:
- Redact PII: phone numbers, physical addresses, account numbers, personal IDs, passwords.
- Redact confidential business content: deal terms, pricing, unreleased financials.
- Preserve the task intent and actionable meaning; do not remove the work request."""

_INPUT_DESCRIPTION = """The user message contains Email context: metadata, Known users, Kind, optional Task history summary, optional Thread history, and Current message (the message to process)."""

_CREATE_DECISION_RULES = """Set should_create=false for pure FYI/ack with no ask.
Set should_create=true when the recipient must read, review, respond, submit, decide, or complete work.

Kind original — create when the recipient is asked to act; skip otherwise.
Kind reply — Current message decides; Thread history is context only (links, subject, prior FYI):
  create on directives ("Read this", "Please review", "Take a look") even after FYI-only thread;
  skip acks/commentary alone ("Thanks", "Noted", "Worth a good read").
Kind forwarded — create if an unresolved ask remains in nested content; skip if answered/closed or no ask."""

_CREATE_OUTPUT_RULES = """Return should_create, confidence (0.0–1.0), and task fields when creating.
If should_create=false: null title/summary, [] assignees.
If should_create=true: title (short, action-oriented), description (imperative, max 2 sentences), summary, status (to_do unless clearly otherwise), priority, due_date, assignees."""

_UPDATE_OUTPUT_RULES = """Always return summary.
Return due_date, assignees, status, title, description, priority only when explicitly changed for the main task work (from Task history summary).
Do not change due_date or priority for sub-tasks, reminders, scheduling side-steps, or nudges about separate steps — record those in summary only; leave due_date and priority null.
When the main task due_date changes, also return priority aligned to it. When main-task urgency wording changes, update priority even if due_date is unchanged.
FYI/reminder with no other main-task changes: summary only; other fields null.
status=done only when Current message clearly completes the original work — not for reminder acks or nudges or sub-task completion. If explicitly stated "done" or "completed" without mentioning any specific steps or sub-tasks, update status to done."""

_ASSIGNEE_RULES_UPDATE = """Return assignees null (not []) unless Current message explicitly reassigns (@mention handoff, assign/reassign, @team).
Do not infer assignees from To/Cc/Bcc, coverage, or reply participants.
When reassigning, return the full new assignee list as Known user emails only."""


def _coverage_map(known_users: list[KnownUser]) -> str:
    lines = []
    for user in known_users:
        topics = [t.strip() for t in (user.coverage_topics or []) if t and str(t).strip()]
        if not topics:
            continue
        label = user.display_name.strip() if user.display_name and user.display_name.strip() else user.email
        lines.append(f"- {label} — {', '.join(topics)}")
    return "\n".join(lines)


def _assignee_rules_create(llm_ctx: LLMEmailContext) -> str:
    coverage = _coverage_map(llm_ctx.known_users)
    coverage_block = (
        f"Coverage map:\n{coverage}"
        if coverage
        else "Coverage map: none configured."
    )
    return f"""Assignees must be emails from Known users only. Union and dedupe:
1. @mentions in Current message matching Known users
2. @team → all Known users
3. Every Known user on To/Cc/Bcc
4. Coverage: infer the sector/region/theme discussed in Subject + Current message; match by meaning to Coverage map topics (not exact words). Add each mapped person who is a Known user.
{coverage_block}
If none match, return []."""


def _build_system_prompt(sections: list[str]) -> str:
    return "\n\n".join(sections)


def update_existing_task_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    system = _build_system_prompt(
        [
            _section("Role", "You are an email task updater for a task management system."),
            _section(
                "Task",
                "An existing task matches this email thread. Produce structured task updates from the Current message.",
            ),
            _section("Input", _INPUT_DESCRIPTION),
            _section("Output", _UPDATE_OUTPUT_RULES),
            _section("Field rules", _FIELD_RULES),
            _section("Assignee rules", _ASSIGNEE_RULES_UPDATE),
            _section("Sanitization", _SANITIZATION_RULES),
        ]
    )
    return system, _format_email_context(llm_ctx)


def create_or_skip_prompt(llm_ctx: LLMEmailContext) -> tuple[str, str]:
    system = _build_system_prompt(
        [
            _section("Role", "You are an email task analyzer for a task management system."),
            _section(
                "Task",
                "No existing task matches this email. Decide whether to create a task and extract fields if so.",
            ),
            _section("Input", _INPUT_DESCRIPTION),
            _section("Decision rules", _CREATE_DECISION_RULES),
            _section("Output", _CREATE_OUTPUT_RULES),
            _section("Field rules", _FIELD_RULES),
            _section("Assignee rules", _assignee_rules_create(llm_ctx)),
            _section("Sanitization", _SANITIZATION_RULES),
        ]
    )
    return system, _format_email_context(llm_ctx)
