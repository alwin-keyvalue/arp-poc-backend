from app.dev.schemas import AnalyzeDebugResponse, LLMCallTrace
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    EmailInput,
    IntentResponse,
    IntentType,
    to_llm_context,
)
from app.services.email_analysis.analyzer import _INTENT_TO_ACTION, _INTENT_TO_PAYLOAD_MODEL, Analyzer
from app.services.email_analysis.prompt_builder import extraction_prompt, intent_prompt


async def analyze_with_trace(analyzer: Analyzer, email: EmailInput) -> AnalyzeDebugResponse:
    llm_ctx = to_llm_context(email)
    calls: list[LLMCallTrace] = []

    system, user = intent_prompt(llm_ctx)
    intent_result = await analyzer._llm.generate(system, user, IntentResponse)
    calls.append(
        LLMCallTrace(
            stage="1_intent",
            system=system,
            user=user,
            output=intent_result.model_dump(mode="json"),
        )
    )

    if intent_result.intent == IntentType.FYI_ONLY:
        result = AnalyzeResponse(
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            action=ActionType.IGNORE,
            payload=None,
        )
        calls.append(
            LLMCallTrace(
                stage="2_extraction",
                system="",
                user="",
                output=None,
                skipped=True,
            )
        )
        return AnalyzeDebugResponse(
            email_input=email,
            llm_context=llm_ctx,
            calls=calls,
            result=result,
        )

    payload_model = _INTENT_TO_PAYLOAD_MODEL[intent_result.intent]
    system, user = extraction_prompt(intent_result.intent, llm_ctx)
    payload = await analyzer._llm.generate(system, user, payload_model)
    calls.append(
        LLMCallTrace(
            stage="2_extraction",
            system=system,
            user=user,
            output=payload.model_dump(mode="json"),
        )
    )

    result = AnalyzeResponse(
        intent=intent_result.intent,
        confidence=intent_result.confidence,
        action=_INTENT_TO_ACTION[intent_result.intent],
        payload=payload,
    )
    return AnalyzeDebugResponse(
        email_input=email,
        llm_context=llm_ctx,
        calls=calls,
        result=result,
    )
