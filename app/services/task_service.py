import logging
import uuid
from typing import List, Optional, Sequence

from fastapi import HTTPException, status

from app.models.task import Task
from app.models.task_status_history import TaskStatusHistory
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    SummaryUpdatePayload,
    TaskCreatePayload,
    TaskUpdatePayload,
)
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

    def _validate_assignees(self, assignee_ids: Optional[List[uuid.UUID]]) -> None:
        for assignee_id in assignee_ids or []:
            if self.user_repository.get_by_id(assignee_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Assignee {assignee_id} not found"
                )

    async def create_task(
        self,
        task_data: TaskCreate,
        *,
        source: str = "api",
        actor_oid: Optional[str] = None,
        actor_name: Optional[str] = None,
    ) -> Task:
        self._validate_assignees(task_data.assignee_ids)
        task = self.repository.create(task_data)
        self.history_repository.record(
            task=task,
            from_status=None,
            to_status=task.status,
            source=source,
            changed_by_oid=actor_oid,
            changed_by_name=actor_name,
        )
        for assignee in task.assignees:
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
        self._validate_assignees(task_data.assignee_ids)
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

    @staticmethod
    def _dedupe(values: Sequence[str]) -> List[str]:
        return list(dict.fromkeys(v for v in values if v))

    def _merged_conversation_ids(
        self,
        task: Task | None,
        *,
        conversation_ids: Sequence[str] | None = None,
        conversation_id: str | None = None,
    ) -> List[str]:
        merged_conv = list(task.conversation_ids) if task is not None else []
        if conversation_ids:
            merged_conv.extend(conversation_ids)
        if conversation_id:
            merged_conv.append(conversation_id)
        return self._dedupe(merged_conv)

    async def apply_analysis(
        self,
        analysis: AnalyzeResponse,
        metadata: ParsedEmailInput,
        from_address: Optional[str],
        *,
        created_via: Optional[str] = None,
        existing_task: Optional[Task] = None,
        thread_conversation_ids: Optional[List[str]] = None,
    ) -> Optional[Task]:
        if analysis.action == ActionType.REMINDER:
            logger.info(
                "Reminder/follow-up detected for conversation %s; no task action taken",
                metadata.conversation_id,
            )
            return None

        seed_conversation_ids = list(thread_conversation_ids or [])
        if metadata.conversation_id:
            seed_conversation_ids.append(metadata.conversation_id)

        if analysis.action == ActionType.IGNORE:
            if existing_task is None:
                logger.info(
                    "FYI-only email for conversation %s has no existing task to update; skipping",
                    metadata.conversation_id,
                )
                return None
            summary = None
            if isinstance(analysis.payload, SummaryUpdatePayload):
                summary = analysis.payload.summary
            if not summary:
                logger.warning(
                    "FYI with existing task %s but no summary; merging ids only",
                    existing_task.id,
                )
            conversation_ids = self._merged_conversation_ids(
                existing_task,
                conversation_ids=seed_conversation_ids,
            )
            update_kwargs: dict = {
                "conversation_ids": conversation_ids,
            }
            if summary:
                update_kwargs["summary"] = summary
            return self.update_task(
                existing_task.id,
                TaskUpdate(**update_kwargs),
                source="email_analysis",
            )

        if analysis.action == ActionType.CREATE:
            if not isinstance(analysis.payload, TaskCreatePayload):
                logger.warning(
                    "CREATE action had unexpected payload type %s for conversation %s; skipping",
                    type(analysis.payload).__name__,
                    metadata.conversation_id,
                )
                return None
            payload_data = analysis.payload.model_dump(exclude={"assignees"})
            conversation_ids = self._merged_conversation_ids(
                None,
                conversation_ids=seed_conversation_ids,
            )
            task_data = TaskCreate(
                **payload_data,
                assignee_ids=self._resolve_assignee_ids(analysis.payload.assignees),
                source_email_id=metadata.message_id,
                conversation_ids=conversation_ids,
                created_via=created_via,
                source_user=from_address,
                source_link=metadata.web_link,
            )
            return await self.create_task(task_data, source="email_analysis")

        if analysis.action == ActionType.UPDATE:
            if not isinstance(analysis.payload, TaskUpdatePayload):
                logger.warning(
                    "UPDATE action had unexpected payload type %s for conversation %s; skipping",
                    type(analysis.payload).__name__,
                    metadata.conversation_id,
                )
                return None
            task = existing_task
            if task is None:
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
            update_data = analysis.payload.model_dump(exclude_none=True, exclude={"assignees"})
            if analysis.payload.assignees is not None:
                update_data["assignee_ids"] = self._resolve_assignee_ids(analysis.payload.assignees)
            update_data["conversation_ids"] = self._merged_conversation_ids(
                task,
                conversation_ids=seed_conversation_ids,
            )
            return self.update_task(
                task.id,
                TaskUpdate(**update_data),
                source="email_analysis",
            )

        logger.warning(
            "Unhandled analysis action %s for conversation %s; no task action taken",
            analysis.action.value,
            metadata.conversation_id,
        )
        return None

    def _resolve_assignee_ids(self, assignees: Optional[List[str]]) -> List[uuid.UUID]:
        ids: List[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for value in assignees or []:
            user = self.user_repository.find_by_name_or_email(value)
            if user is None:
                logger.warning("Could not resolve assignee '%s' to a known user; skipping", value)
                continue
            if user.id in seen:
                continue
            seen.add(user.id)
            ids.append(user.id)
        return ids
