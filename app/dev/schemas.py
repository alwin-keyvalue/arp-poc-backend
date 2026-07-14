from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.email_analysis import AnalyzeResponse, EmailInput, LLMEmailContext


class LLMCallTrace(BaseModel):
    stage: str
    system: str
    user: str
    output: Optional[dict[str, Any]] = None
    skipped: bool = False


class AnalyzeDebugResponse(BaseModel):
    email_input: EmailInput
    llm_context: LLMEmailContext
    calls: list[LLMCallTrace]
    result: AnalyzeResponse


class WebhookTraceSummary(BaseModel):
    id: str
    received_at: datetime
    message_id: str
    user_email: str
    subject: Optional[str] = None
    intent: str
    action: str
    confidence: float


class WebhookTraceDetail(BaseModel):
    id: str
    received_at: datetime
    message_id: str
    user_email: str
    subject: Optional[str] = None
    calls: list[LLMCallTrace]
    result: AnalyzeResponse
