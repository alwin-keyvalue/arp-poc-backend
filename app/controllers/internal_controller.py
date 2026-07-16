import enum
import functools
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

import httpx
from fastapi import APIRouter, Body, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.dependencies import get_analyzer, get_http_client
from app.services.mailbox_sync_service import MailboxSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class JobName(str, enum.Enum):
    SYNC_MAILBOXES = "sync_mailboxes"


class JobParams(BaseModel):
    """Base for job param schemas — forbids unknown keys so a typo (e.g. "lookback_day")
    is rejected as a 422 rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


class SyncMailboxesParams(JobParams):
    lookback_days: Optional[int] = Field(default=None, ge=1, le=365)
    # When omitted, every subscribed user's mailbox is synced; when given, only these.
    user_ids: Optional[List[uuid.UUID]] = Field(default=None, min_length=1)


def _build_sync_mailboxes_job(
    http_client: httpx.AsyncClient, params: SyncMailboxesParams
) -> Callable[[], Awaitable[Any]]:
    # This job needs an LLM analyzer; others may not, so it's fetched here rather than
    # threaded through run_job's shared signature for every job regardless of need.
    analyzer = get_analyzer()
    lookback_days = params.lookback_days if params.lookback_days is not None else settings.mailbox_sync_lookback_days
    service = MailboxSyncService(http_client, analyzer, lookback_days=lookback_days)
    # A plain lambda wrapping this call would NOT be awaited by BackgroundTasks: Starlette
    # decides sync-vs-async by is_async_callable(func), which only unwraps functools.partial
    # (not lambdas) before checking asyncio.iscoroutinefunction — a lambda body that returns
    # a coroutine gets run in a threadpool and the coroutine it returns is silently dropped,
    # never awaited (no error, no logs, the job just doesn't run).
    return functools.partial(service.sync_all_users, user_ids=params.user_ids)


@dataclass(frozen=True)
class JobSpec:
    params_model: Type[JobParams]
    factory: Callable[[httpx.AsyncClient, Any], Callable[[], Awaitable[Any]]]


JOB_REGISTRY: Dict[JobName, JobSpec] = {
    JobName.SYNC_MAILBOXES: JobSpec(params_model=SyncMailboxesParams, factory=_build_sync_mailboxes_job),
}
assert set(JOB_REGISTRY) == set(JobName), "JOB_REGISTRY must have exactly one entry per JobName"


def _verify_sync_secret(x_internal_secret: str = Header(...)) -> None:
    if not settings.internal_sync_secret or x_internal_secret != settings.internal_sync_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing sync secret")


@router.post(
    "/jobs/{job_name}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_verify_sync_secret)],
)
async def run_job(
    job_name: JobName,
    background_tasks: BackgroundTasks,
    raw_params: Dict[str, Any] = Body(default={}),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    spec = JOB_REGISTRY[job_name]
    try:
        params = spec.params_model.model_validate(raw_params)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

    job = spec.factory(http_client, params)
    logger.info(
        "Queuing job '%s' for background processing (params=%s)",
        job_name.value,
        params.model_dump(exclude_none=True),
    )
    background_tasks.add_task(job)
    return {"status": "queued", "job": job_name.value}
