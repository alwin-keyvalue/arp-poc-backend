from typing import List, Type

from pydantic import BaseModel

from app.config import Settings, settings
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    EmailInput,
    IntentResponse,
    IntentType,
    KnownUser,
    ReminderPayload,
    SummaryUpdatePayload,
    TaskCreatePayload,
    TaskUpdatePayload,
    to_llm_context,
)
from app.services.email_analysis.llm.factory import create_llm_client
from app.services.email_analysis.llm_service import LLMService
from app.services.email_analysis.prompt_builder import (
    extraction_prompt,
    intent_prompt,
    summary_update_prompt,
)

_INTENT_TO_ACTION = {
    IntentType.NEW_TASK: ActionType.CREATE,
    IntentType.FYI_ONLY: ActionType.IGNORE,
    IntentType.TASK_UPDATE: ActionType.UPDATE,
    IntentType.REMINDER_FOLLOW_UP: ActionType.REMINDER,
}

_INTENT_TO_PAYLOAD_MODEL: dict[IntentType, Type[BaseModel]] = {
    IntentType.NEW_TASK: TaskCreatePayload,
    IntentType.TASK_UPDATE: TaskUpdatePayload,
    IntentType.REMINDER_FOLLOW_UP: ReminderPayload,
}


def _match_known_user_email(value: str, known_users: List[KnownUser]) -> str | None:
    needle = value.strip().lstrip("@").lower()
    if not needle:
        return None
    for user in known_users:
        email = user.email.strip().lower()
        if needle == email or needle == email.split("@", 1)[0]:
            return user.email
        if user.display_name and needle == user.display_name.strip().lower():
            return user.email
        if user.display_name and user.display_name.strip().lower().startswith(needle + " "):
            return user.email
    return None


def _filter_assignees_to_known_users(
    assignees: List[str] | None,
    known_users: List[KnownUser] | None,
) -> List[str]:
    if not assignees or not known_users:
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for raw in assignees:
        email = _match_known_user_email(raw, known_users)
        if email is None:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        matched.append(email)
    return matched


def _known_recipient_emails(
    email: EmailInput,
    known_users: List[KnownUser] | None,
) -> List[str]:
    if not known_users:
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for raw in [*email.to, *email.cc, *email.bcc]:
        found = _match_known_user_email(raw, known_users)
        if found is None:
            continue
        key = found.lower()
        if key in seen:
            continue
        seen.add(key)
        matched.append(found)
    return matched


def _finalize_assignees(
    assignees: List[str] | None,
    email: EmailInput,
    known_users: List[KnownUser] | None,
) -> List[str]:
    """Filter to Known users, then always union Known To/Cc/Bcc recipients."""
    finalized = _filter_assignees_to_known_users(assignees, known_users)
    seen = {e.lower() for e in finalized}
    for recipient in _known_recipient_emails(email, known_users):
        key = recipient.lower()
        if key in seen:
            continue
        seen.add(key)
        finalized.append(recipient)
    return finalized


class Analyzer:
    def __init__(self, llm: LLMService):
        self._llm = llm

    async def analyze(
        self,
        email: EmailInput,
        known_users: List[KnownUser] | None = None,
        task_summary: str | None = None,
        thread_context: str | None = None,
        refresh_summary_on_fyi: bool = False,
    ) -> AnalyzeResponse:
        llm_ctx = to_llm_context(
            email,
            known_users=known_users,
            task_summary=task_summary,
            thread_context=thread_context,
        )

        system, user = intent_prompt(llm_ctx)
        intent_result = await self._llm.generate(system, user, IntentResponse)

        if intent_result.intent == IntentType.FYI_ONLY:
            payload = None
            if refresh_summary_on_fyi:
                system, user = summary_update_prompt(llm_ctx)
                payload = await self._llm.generate(system, user, SummaryUpdatePayload)
            return AnalyzeResponse(
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                action=ActionType.IGNORE,
                payload=payload,
            )

        payload_model = _INTENT_TO_PAYLOAD_MODEL[intent_result.intent]
        system, user = extraction_prompt(intent_result.intent, llm_ctx)
        payload = await self._llm.generate(system, user, payload_model)

        if isinstance(payload, (TaskCreatePayload, TaskUpdatePayload)) and payload.assignees is not None:
            payload.assignees = _finalize_assignees(payload.assignees, email, known_users)

        return AnalyzeResponse(
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            action=_INTENT_TO_ACTION[intent_result.intent],
            payload=payload,
        )


def create_analyzer(app_settings: Settings | None = None) -> Analyzer:
    cfg = app_settings or settings
    return Analyzer(LLMService(create_llm_client(cfg)))
