from typing import List

from app.config import Settings, settings
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    CreateOrSkipPayload,
    EmailInput,
    IntentType,
    KnownUser,
    TaskCreatePayload,
    TaskUpdatePayload,
    to_llm_context,
)
from app.services.email_analysis.llm.factory import create_llm_client
from app.services.email_analysis.llm_service import LLMService
from app.services.email_analysis.prompt_builder import (
    create_or_skip_prompt,
    update_existing_task_prompt,
)


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
        has_existing_task: bool = False,
    ) -> AnalyzeResponse:
        llm_ctx = to_llm_context(
            email,
            known_users=known_users,
            task_summary=task_summary,
            thread_context=thread_context,
        )

        if has_existing_task:
            system, user = update_existing_task_prompt(llm_ctx)
            payload = await self._llm.generate(system, user, TaskUpdatePayload)
            if payload.assignees is not None:
                payload.assignees = _filter_assignees_to_known_users(payload.assignees, known_users)
                if not payload.assignees:
                    payload.assignees = None
            return AnalyzeResponse(
                intent=IntentType.TASK_UPDATE,
                confidence=1.0,
                action=ActionType.UPDATE,
                payload=payload,
            )

        system, user = create_or_skip_prompt(llm_ctx)
        result = await self._llm.generate(system, user, CreateOrSkipPayload)

        if not result.should_create:
            return AnalyzeResponse(
                intent=IntentType.FYI_ONLY,
                confidence=result.confidence,
                action=ActionType.IGNORE,
                payload=None,
            )

        create_payload = TaskCreatePayload(
            title=result.title or "",
            description=result.description,
            summary=result.summary or "",
            assignees=result.assignees,
            status=result.status,
            priority=result.priority,
            due_date=result.due_date,
        )
        create_payload.assignees = _finalize_assignees(create_payload.assignees, email, known_users)
        return AnalyzeResponse(
            intent=IntentType.NEW_TASK,
            confidence=result.confidence,
            action=ActionType.CREATE,
            payload=create_payload,
        )


def create_analyzer(app_settings: Settings | None = None) -> Analyzer:
    cfg = app_settings or settings
    return Analyzer(LLMService(create_llm_client(cfg)))
