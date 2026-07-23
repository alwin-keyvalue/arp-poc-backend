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
from app.models.task import TaskPriority
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.label import LabelResponse
from app.schemas.task import (
    TaskCreate,
    TaskDashboardResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
    TaskActivityPage,
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
        TaskChangeHistoryRepository(db),
        LabelRepository(db),
        NoteRepository(db),
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return await service.create_task(task_data, actor_oid=actor.oid, actor_name=actor.display_label)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Case-insensitive match on title, description, or summary"),
    assignee_id: Optional[uuid.UUID] = Query(None, description="Only tasks assigned to this user"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority (P0, P1, P2)"),
    created_on: Optional[date] = Query(None, description="Only tasks created on this date (YYYY-MM-DD)"),
    due_on: Optional[date] = Query(None, description="Only tasks due on this date (YYYY-MM-DD)"),
    label: Optional[str] = Query(None, description="Only tasks that include this label"),
    scope: Optional[str] = Query(
        None,
        description="Dashboard bucket filter: open | overdue | due_this_week | completed",
        pattern="^(open|overdue|due_this_week|completed)$",
    ),
    deleted_only: bool = Query(False, description="If true, return only soft-deleted tasks instead of active ones"),
    service: TaskService = Depends(get_task_service),
):
    items, total = service.get_tasks(
        skip=skip,
        limit=limit,
        search=search,
        assignee_id=assignee_id,
        priority=priority.value if priority is not None else None,
        created_on=created_on,
        due_on=due_on,
        label=label,
        scope=scope,
        deleted_only=deleted_only,
    )
    return TaskListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/dashboard", response_model=TaskDashboardResponse)
def get_dashboard(service: TaskService = Depends(get_task_service)):
    return service.get_dashboard()


@router.get(
    "/stats/users",
    response_model=List[UserTaskStatsResponse],
    dependencies=[Depends(require_admin_user)],
)
def get_user_stats(service: TaskService = Depends(get_task_service)):
    return service.get_user_stats()


@router.get("/activity", response_model=TaskActivityPage)
def get_my_activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    print("actor.oid", actor.oid)
    return service.get_activity_for_user(
        aad_object_id=actor.oid, email=actor.preferred_username, page=page, page_size=page_size
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_with_notes(task_id)


@router.get("/{task_id}/history", response_model=List[TaskChangeHistoryResponse])
def get_task_history(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_history(task_id)


@router.get("/{task_id}/labels", response_model=List[LabelResponse])
def list_task_labels(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_labels(task_id)


@router.post("/{task_id}/labels/{label_id}", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
def attach_task_label(task_id: uuid.UUID, label_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.attach_label(task_id, label_id)


@router.delete("/{task_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_task_label(task_id: uuid.UUID, label_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    service.detach_label(task_id, label_id)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: uuid.UUID,
    task_data: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return service.update_task(task_id, task_data, actor_oid=actor.oid, actor_name=actor.display_label)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    service.delete_task(task_id)
