import uuid
from collections import deque
from datetime import datetime, timezone

from app.dev.schemas import AnalyzeDebugResponse, WebhookTraceDetail, WebhookTraceSummary
from app.schemas.parsed_email import ParsedEmailInput

_MAX_RECORDS = 50
_records: deque[WebhookTraceDetail] = deque(maxlen=_MAX_RECORDS)


def record_trace(debug: AnalyzeDebugResponse, metadata: ParsedEmailInput) -> str:
    trace_id = str(uuid.uuid4())
    detail = WebhookTraceDetail(
        id=trace_id,
        received_at=datetime.now(timezone.utc),
        message_id=metadata.message_id,
        user_email=metadata.user_email,
        subject=debug.email_input.subject,
        calls=debug.calls,
        result=debug.result,
    )
    _records.appendleft(detail)
    return trace_id


def list_traces() -> list[WebhookTraceSummary]:
    return [
        WebhookTraceSummary(
            id=r.id,
            received_at=r.received_at,
            message_id=r.message_id,
            user_email=r.user_email,
            subject=r.subject,
            intent=r.result.intent.value,
            action=r.result.action.value,
            confidence=r.result.confidence,
        )
        for r in _records
    ]


def get_trace(trace_id: str) -> WebhookTraceDetail | None:
    for record in _records:
        if record.id == trace_id:
            return record
    return None
