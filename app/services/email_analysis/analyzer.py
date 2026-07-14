from typing import Type

from pydantic import BaseModel

from app.config import Settings, settings
from app.schemas.conversation import ConversationMessagesResponse
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    IntentResponse,
    IntentType,
    ReminderPayload,
    TaskCreatePayload,
    TaskUpdatePayload,
    to_llm_context,
)
from app.schemas.parsed_email import ParsedEmailInput
from app.services.email_analysis.llm.factory import create_llm_client
from app.services.email_analysis.llm_service import LLMService
from app.services.email_analysis.prompt_builder import extraction_prompt, intent_prompt

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


class Analyzer:
    def __init__(self, llm: LLMService):
        self._llm = llm

    async def analyze(
        self,
        email: ParsedEmailInput,
        conversation: ConversationMessagesResponse | None = None,
    ) -> AnalyzeResponse:
        llm_ctx = to_llm_context(email, conversation)

        system, user = intent_prompt(llm_ctx)
        intent_result = await self._llm.generate(system, user, IntentResponse)

        if intent_result.intent == IntentType.FYI_ONLY:
            return AnalyzeResponse(
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                action=ActionType.IGNORE,
                payload=None,
            )

        payload_model = _INTENT_TO_PAYLOAD_MODEL[intent_result.intent]
        system, user = extraction_prompt(intent_result.intent, llm_ctx)
        payload = await self._llm.generate(system, user, payload_model)

        return AnalyzeResponse(
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            action=_INTENT_TO_ACTION[intent_result.intent],
            payload=payload,
        )


def create_analyzer(app_settings: Settings | None = None) -> Analyzer:
    cfg = app_settings or settings
    return Analyzer(LLMService(create_llm_client(cfg)))
