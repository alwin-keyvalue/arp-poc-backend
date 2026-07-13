from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.dev.store import get_trace, list_traces
from app.dev.schemas import WebhookTraceDetail, WebhookTraceSummary
from fastapi.responses import FileResponse

router = APIRouter(prefix="/dev/llm", tags=["dev"])

_UI_PATH = Path(__file__).resolve().parent / "llm_debug.html"


@router.get("")
def llm_debug_ui():
    return FileResponse(_UI_PATH)


@router.get("/events", response_model=list[WebhookTraceSummary])
def list_webhook_traces():
    return list_traces()


@router.get("/events/{trace_id}", response_model=WebhookTraceDetail)
def get_webhook_trace(trace_id: str):
    trace = get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
