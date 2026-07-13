import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.models.task import Task
from app.repositories.task_repository import TaskRepository
from app.schemas.email_analysis import ActionType, AnalyzeResponse
from app.schemas.parsed_email import GraphMessageMetadata
from app.schemas.task import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def create_task(self, task_data: TaskCreate) -> Task:
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
        return self.repository.update(task, task_data)

    def delete_task(self, task_id: uuid.UUID) -> None:
        task = self.get_task(task_id)
        self.repository.delete(task)

    def apply_analysis(
        self,
        analysis: AnalyzeResponse,
        metadata: GraphMessageMetadata,
        from_address: Optional[str],
    ) -> Optional[Task]:
        if analysis.action == ActionType.IGNORE or analysis.action == ActionType.REMINDER:
            return None

        if analysis.action == ActionType.CREATE:
            if not isinstance(analysis.payload, TaskCreate):
                return None
            task_data = analysis.payload.model_copy(
                update={
                    "source_email_id": metadata.message_id,
                    "conversation_id": metadata.conversation_id,
                    "source_user": from_address,
                    "source_link": metadata.web_link,
                }
            )
            return self.create_task(task_data)

        if analysis.action == ActionType.UPDATE:
            if not isinstance(analysis.payload, TaskUpdate):
                return None
            if not metadata.conversation_id:
                logger.warning("Cannot update task: missing conversation_id")
                return None
            task = self.repository.get_by_conversation_id(metadata.conversation_id)
            if task is None:
                logger.warning(
                    "Cannot update task: no task for conversation_id %s",
                    metadata.conversation_id,
                )
                return None
            return self.update_task(task.id, analysis.payload)

        return None
