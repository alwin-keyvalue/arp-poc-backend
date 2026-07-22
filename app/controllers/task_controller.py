import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.teams_auth import TeamsUser, get_current_teams_user
from app.database import get_db
from app.models.task import TaskPriority
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import (
    TaskCreate,
    TaskDashboardResponse,
    TaskListResponse,
    TaskResponse,
    TaskStatusHistoryResponse,
    TaskUpdate,
)
from app.services.bot_service import BotService, get_bot_service
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_teams_user)])


def get_task_service(
    db: Session = Depends(get_db),
    bot_service: BotService = Depends(get_bot_service),
) -> TaskService:
    return TaskService(TaskRepository(db), UserRepository(db), bot_service, TaskStatusHistoryRepository(db))


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
    service: TaskService = Depends(get_task_service),
):
    items, total = service.get_tasks(
        skip=skip,
        limit=limit,
        search=search,
        assignee_id=assignee_id,
        priority=priority.value if priority is not None else None,
        created_on=created_on,
    )
    return TaskListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/dashboard", response_model=TaskDashboardResponse)
def get_dashboard(service: TaskService = Depends(get_task_service)):
    return service.get_dashboard()


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task(task_id)


@router.get("/{task_id}/history", response_model=List[TaskStatusHistoryResponse])
def get_task_history(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task_history(task_id)


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
