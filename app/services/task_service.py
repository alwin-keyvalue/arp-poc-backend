import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.models.task import Task
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, repository: TaskRepository, user_repository: UserRepository):
        self.repository = repository
        self.user_repository = user_repository

    def _validate_assignee(self, assignee_id: Optional[uuid.UUID]) -> None:
        if assignee_id is None:
            return
        if self.user_repository.get_by_id(assignee_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    def create_task(self, task_data: TaskCreate) -> Task:
        self._validate_assignee(task_data.assignee_id)
        return self.repository.create(task_data)

    def get_task(self, task_id: uuid.UUID) -> Task:
        task = self.repository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    def get_tasks(self, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_all(skip=skip, limit=limit)

    def update_task(self, task_id: uuid.UUID, task_data: TaskUpdate) -> Task:
        task = self.get_task(task_id)
        self._validate_assignee(task_data.assignee_id)
        return self.repository.update(task, task_data)

    def delete_task(self, task_id: uuid.UUID) -> None:
        task = self.get_task(task_id)
        self.repository.delete(task)
