import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.models.task import Task
from app.models.task_status_history import TaskStatusHistory
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import ActionType, AnalyzeResponse, TaskCreatePayload, TaskUpdatePayload
from app.schemas.parsed_email import ParsedEmailInput
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.bot_service import BotService

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        user_repository: UserRepository,
        bot_service: BotService,
        history_repository: TaskStatusHistoryRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.bot_service = bot_service
        self.history_repository = history_repository

    def _validate_assignee(self, assignee_id: Optional[uuid.UUID]) -> None:
        if assignee_id is None:
            return
        if self.user_repository.get_by_id(assignee_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    async def create_task(
        self,
        task_data: TaskCreate,
        *,
        source: str = "api",
        actor_oid: Optional[str] = None,
        actor_name: Optional[str] = None,
    ) -> Task:
        self._validate_assignee(task_data.assignee_id)
        task = self.repository.create(task_data)
        self.history_repository.record(
            task=task,
            from_status=None,
            to_status=task.status,
            source=source,
            changed_by_oid=actor_oid,
            changed_by_name=actor_name,
        )
        if task.assignee_id:
            assignee = self.user_repository.get_by_id(task.assignee_id)
            if assignee:
                await self.bot_service.notify_task_assigned(assignee, task)
        return task

    def get_task(self, task_id: uuid.UUID) -> Task:
        task = self.repository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    def get_tasks(self, skip: int = 0, limit: int = 100) -> List[Task]:
        return self.repository.get_all(skip=skip, limit=limit)

    def get_task_history(self, task_id: uuid.UUID) -> List[TaskStatusHistory]:
        self.get_task(task_id)
        return self.history_repository.list_for_task(task_id)

    def update_task(
        self,
        task_id: uuid.UUID,
        task_data: TaskUpdate,
        *,
        source: str = "api",
        actor_oid: Optional[str] = None,
        actor_name: Optional[str] = None,
    ) -> Task:
        task = self.get_task(task_id)
        self._validate_assignee(task_data.assignee_id)
        previous_status = task.status
        updated = self.repository.update(task, task_data)
        status_changed = "status" in task_data.model_fields_set and updated.status != previous_status
        if status_changed:
            self.history_repository.record(
                task=updated,
                from_status=previous_status,
                to_status=updated.status,
                source=source,
                changed_by_oid=actor_oid,
                changed_by_name=actor_name,
            )
        return updated

    def delete_task(self, task_id: uuid.UUID) -> None:
        task = self.get_task(task_id)
        self.repository.soft_delete(task)

    async def apply_analysis(
        self,
        analysis: AnalyzeResponse,
        metadata: ParsedEmailInput,
        from_address: Optional[str],
    ) -> Optional[Task]:
        if analysis.action == ActionType.IGNORE or analysis.action == ActionType.REMINDER:
            return None

        if analysis.action == ActionType.CREATE:
            if not isinstance(analysis.payload, TaskCreatePayload):
                return None
            task_data = TaskCreate(
                **analysis.payload.model_dump(),
                source_email_id=metadata.message_id,
                conversation_id=metadata.conversation_id,
                source_user=from_address,
                source_link=metadata.web_link,
            )
            return await self.create_task(task_data, source="email_analysis")

        if analysis.action == ActionType.UPDATE:
            if not isinstance(analysis.payload, TaskUpdatePayload):
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
            return self.update_task(
                task.id,
                TaskUpdate(**analysis.payload.model_dump(exclude_none=True)),
                source="email_analysis",
            )

        return None
