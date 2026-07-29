import enum
import functools
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

import httpx
from fastapi import APIRouter, Body, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, model_validator

from app.config import settings
from app.core.internal_auth import verify_internal_auth_secret
from app.dependencies import get_analyzer, get_http_client
from app.services.mailbox_sync_service import MailboxSyncService
from app.services.report_service import default_report_date_range, run_task_report
from app.services.subscription_service import run_renew_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class JobName(str, enum.Enum):
    SYNC_MAILBOXES = "sync_mailboxes"
    RENEW_GRAPH_SUBSCRIPTION = "renew_graph_subscription"
    TASK_REPORT = "task_report"


class JobParams(BaseModel):
    """Base for job param schemas — forbids unknown keys so a typo (e.g. "lookback_day")
    is rejected as a 422 rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


class SyncMailboxesParams(JobParams):
    lookback_days: Optional[int] = Field(default=None, ge=1, le=365)
    # When omitted, every subscribed user's mailbox is synced; when given, only these.
    user_ids: Optional[List[uuid.UUID]] = Field(default=None, min_length=1)


class RenewGraphSubscriptionParams(JobParams):
    """No parameters — renews every Graph subscription on record."""


class TaskReportParams(JobParams):
    recipients: List[EmailStr] = Field(min_length=1)
    # Omitted dates default to yesterday; a single date fills the other side.
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    @model_validator(mode="after")
    def resolve_date_range(self) -> "TaskReportParams":
        if self.from_date is None and self.to_date is None:
            self.from_date, self.to_date = default_report_date_range()
        elif self.from_date is None:
            self.from_date = self.to_date
        elif self.to_date is None:
            self.to_date = self.from_date
        if self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


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


def _build_renew_graph_subscription_job(
    http_client: httpx.AsyncClient, _params: RenewGraphSubscriptionParams
) -> Callable[[], Awaitable[Any]]:
    return functools.partial(run_renew_all, http_client)


def _build_task_report_job(
    http_client: httpx.AsyncClient, params: TaskReportParams
) -> Callable[[], Awaitable[Any]]:
    return functools.partial(
        run_task_report,
        http_client,
        params.from_date,
        params.to_date,
        [str(recipient) for recipient in params.recipients],
    )


@dataclass(frozen=True)
class JobSpec:
    params_model: Type[JobParams]
    factory: Callable[[httpx.AsyncClient, Any], Callable[[], Awaitable[Any]]]


JOB_REGISTRY: Dict[JobName, JobSpec] = {
    JobName.SYNC_MAILBOXES: JobSpec(params_model=SyncMailboxesParams, factory=_build_sync_mailboxes_job),
    JobName.RENEW_GRAPH_SUBSCRIPTION: JobSpec(
        params_model=RenewGraphSubscriptionParams,
        factory=_build_renew_graph_subscription_job,
    ),
    JobName.TASK_REPORT: JobSpec(params_model=TaskReportParams, factory=_build_task_report_job),
}
assert set(JOB_REGISTRY) == set(JobName), "JOB_REGISTRY must have exactly one entry per JobName"


@router.post(
    "/jobs/{job_name}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_internal_auth_secret)],
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
        # include_context=False: ctx can hold raw Exception objects that aren't JSON-serializable.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_context=False),
        ) from exc

    job = spec.factory(http_client, params)
    logger.info(
        "Queuing job '%s' for background processing (params=%s)",
        job_name.value,
        params.model_dump(exclude_none=True),
    )
    background_tasks.add_task(job)
    return {"status": "queued", "job": job_name.value}
