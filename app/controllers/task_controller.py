import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.teams_auth import TeamsUser, get_current_teams_user, require_admin_user
from app.database import get_db
from app.repositories.label_repository import LabelRepository
from app.repositories.note_repository import NoteRepository
from app.repositories.task_change_history_repository import TaskChangeHistoryRepository
from app.repositories.task_change_notification_repository import TaskChangeNotificationRepository
from app.models.task import TaskPriority, TaskStatus
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.label import LabelResponse
from app.schemas.notification import TaskNotificationPage
from app.schemas.task import (
    TaskCreate,
    TaskDashboardResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
    TaskChangeHistoryResponse,
    UserTaskStatsResponse,
)
from app.services.bot_service import BotService, get_bot_service
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_teams_user)])


def get_task_service(
    db: Session = Depends(get_db),
    bot_service: BotService = Depends(get_bot_service),
) -> TaskService:
    return TaskService(
        TaskRepository(db),
        UserRepository(db),
        bot_service,
        TaskChangeHistoryRepository(db, bot_service),
        LabelRepository(db),
        NoteRepository(db),
        TaskChangeNotificationRepository(db),
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return await service.create_task(task_data, actor_oid=actor.oid)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Case-insensitive match on title, description, or summary"),
    assignee_ids: Optional[List[uuid.UUID]] = Query(
        None, description="Only tasks assigned to any of these users (OR within this filter)"
    ),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority (P0, P1, P2)"),
    status: Optional[TaskStatus] = Query(None, description="Filter by status (to_do, done, dropped)"),
    created_on: Optional[date] = Query(None, description="Only tasks created on this date (YYYY-MM-DD)"),
    due_on: Optional[date] = Query(None, description="Only tasks due on this date (YYYY-MM-DD)"),
    due_from: Optional[date] = Query(None, description="Only tasks due on or after this date (YYYY-MM-DD)"),
    due_to: Optional[date] = Query(None, description="Only tasks due on or before this date (YYYY-MM-DD)"),
    labels: Optional[List[str]] = Query(
        None, description="Only tasks that include any of these labels (OR within this filter)"
    ),
    scope: Optional[str] = Query(
        None,
        description="Dashboard bucket filter: open | overdue | due_this_week | completed",
        pattern="^(open|overdue|due_this_week|completed)$",
    ),
    deleted_only: bool = Query(False, description="If true, return only soft-deleted tasks instead of active ones"),
    filter_operator: str = Query(
        "and",
        description="How to combine the filters above: 'and' (all must match) or 'or' (any one is enough)",
        pattern="^(and|or)$",
    ),
    service: TaskService = Depends(get_task_service),
):
    items, total = service.get_tasks(
        skip=skip,
        limit=limit,
        search=search,
        assignee_ids=assignee_ids,
        priority=priority.value if priority is not None else None,
        status=status.value if status is not None else None,
        created_on=created_on,
        due_on=due_on,
        due_from=due_from,
        due_to=due_to,
        labels=labels,
        scope=scope,
        deleted_only=deleted_only,
        filter_operator=filter_operator,
    )
    return TaskListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/dashboard", response_model=TaskDashboardResponse)
def get_dashboard(
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return service.get_dashboard(aad_object_id=actor.oid, email=actor.preferred_username)


@router.get("/insights", response_model=TaskListResponse)
def get_my_insights(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    items, total = service.get_insights(
        aad_object_id=actor.oid,
        email=actor.preferred_username,
        skip=skip,
        limit=limit,
    )
    return TaskListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/stats/users",
    response_model=List[UserTaskStatsResponse],
    dependencies=[Depends(require_admin_user)],
)
def get_user_stats(service: TaskService = Depends(get_task_service)):
    return service.get_user_stats()


@router.get("/notifications", response_model=TaskNotificationPage)
def get_my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    source: Optional[str] = Query(
        None, description="Filter by task_change_history.source (e.g. api, email_analysis, teams_bot)"
    ),
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return service.get_notifications_for_user(
        aad_object_id=actor.oid,
        email=actor.preferred_username,
        page=page,
        page_size=page_size,
        source=source,
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: uuid.UUID,
    include_deleted: bool = Query(False, description="If true, a soft-deleted task can still be returned"),
    service: TaskService = Depends(get_task_service),
):
    return service.get_task_with_notes(task_id, include_deleted=include_deleted)


@router.get("/{task_id}/history", response_model=List[TaskChangeHistoryResponse])
def get_task_history(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_history(task_id)


@router.get("/{task_id}/labels", response_model=List[LabelResponse])
def list_task_labels(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_labels(task_id)


@router.post("/{task_id}/labels/{label_id}", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
async def attach_task_label(
    task_id: uuid.UUID,
    label_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return await service.attach_label(task_id, label_id, actor_oid=actor.oid)


@router.delete("/{task_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_task_label(
    task_id: uuid.UUID,
    label_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    await service.detach_label(task_id, label_id, actor_oid=actor.oid)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    task_data: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return await service.update_task(task_id, task_data, actor_oid=actor.oid)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    await service.delete_task(task_id, actor_oid=actor.oid)


@router.post("/{task_id}/restore", response_model=TaskResponse)
async def restore_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return await service.restore_task(task_id, actor_oid=actor.oid)
