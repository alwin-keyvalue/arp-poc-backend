import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.bot_service import BotService, get_bot_service
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(
    db: Session = Depends(get_db),
    bot_service: BotService = Depends(get_bot_service),
) -> TaskService:
    return TaskService(TaskRepository(db), UserRepository(db), bot_service)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task_data: TaskCreate, service: TaskService = Depends(get_task_service)):
    return await service.create_task(task_data)


@router.get("", response_model=List[TaskResponse])
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    service: TaskService = Depends(get_task_service),
):
    return service.get_tasks(skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    return service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: uuid.UUID, task_data: TaskUpdate, service: TaskService = Depends(get_task_service)):
    return service.update_task(task_id, task_data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, service: TaskService = Depends(get_task_service)):
    service.delete_task(task_id)
