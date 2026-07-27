import logging
import uuid
from datetime import date
from typing import List, Optional, Sequence, Tuple, Any

from fastapi import HTTPException, status

from app.models.label import Label
from app.models.task import Task
from app.models.task_change_history import TaskChangeHistory
from app.models.user import SYSTEM_USER_ID
from app.repositories.label_repository import LabelRepository
from app.repositories.note_repository import NoteRepository
from app.repositories.task_change_history_repository import TaskChangeHistoryRepository
from app.repositories.task_change_notification_repository import TaskChangeNotificationRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.email_analysis import (
    ActionType,
    AnalyzeResponse,
    TaskCreatePayload,
    TaskUpdatePayload,
)
from app.schemas.note import NoteResponse
from app.schemas.notification import (
    TaskChangeHistoryDetail,
    TaskNotificationPage,
    TaskNotificationResponse,
)
from app.schemas.parsed_email import ParsedEmailInput
from app.schemas.task import (
    TaskCreate,
    TaskDashboardResponse,
    TaskDetailResponse,
    TaskResponse,
    TaskUpdate,
    UserTaskStatsResponse,
)
from app.schemas.user import UserResponse
from app.services.bot_service import BotService

logger = logging.getLogger(__name__)

# Fields worth an audit-trail row when changed via update_task. Internal/bookkeeping fields
# (conversation_ids, internet_message_ids, source_email_id, source_user, source_link) are
# deliberately excluded — they're mutated automatically as a side effect of email threading
# on nearly every apply_analysis call, which would drown real changes in noise.
_TRACKED_FIELDS = {
    "title",
    "description",
    "summary",
    "note",
    "status",
    "priority",
    "due_date",
    "assignee_ids",
}


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        user_repository: UserRepository,
        bot_service: BotService,
        history_repository: TaskChangeHistoryRepository,
        label_repository: LabelRepository,
        note_repository: NoteRepository,
        notification_repository: TaskChangeNotificationRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.bot_service = bot_service
        self.history_repository = history_repository
        self.label_repository = label_repository
        self.note_repository = note_repository
        self.notification_repository = notification_repository

    def _validate_assignees(self, assignee_ids: Optional[List[uuid.UUID]]) -> None:
        for assignee_id in assignee_ids or []:
            if self.user_repository.get_by_id(assignee_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Assignee {assignee_id} not found"
                )

    def _resolve_updated_by(self, actor_oid: Optional[str]) -> uuid.UUID:
        """Automatic changes (no actor_oid — e.g. email/webhook-triggered) and changes whose
        actor can't be resolved to a known User both attribute to the seeded system user
        rather than leaving updated_by null."""
        if actor_oid:
            actor = self.user_repository.get_by_aad_object_id(actor_oid)
            if actor is not None:
                return actor.id
        return SYSTEM_USER_ID

    async def create_task(
        self,
        task_data: TaskCreate,
        *,
        source: str = "api",
        actor_oid: Optional[str] = None,
        processed_email_id: Optional[uuid.UUID] = None,
    ) -> Task:
        self._validate_assignees(task_data.assignee_ids)
        task = self.repository.create(task_data)
        self.history_repository.record(
            task=task,
            field_name="status",
            old_value=None,
            new_value=task.status,
            source=source,
            updated_by=self._resolve_updated_by(actor_oid),
            processed_email_id=processed_email_id,
        )
        for assignee in task.assignees:
            await self.bot_service.notify_task_assigned(assignee, task)
        return task

    def get_task(self, task_id: uuid.UUID) -> Task:
        task = self.repository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    def get_task_with_notes(self, task_id: uuid.UUID) -> TaskDetailResponse:
        task = self.get_task(task_id)
        notes = self.note_repository.list_for_task(task_id)
        return TaskDetailResponse(
            **TaskResponse.model_validate(task).model_dump(),
            notes=[NoteResponse.model_validate(note) for note in notes],
        )

    def get_tasks(
        self,
        skip: int = 0,
        limit: int = 100,
        *,
        search: Optional[str] = None,
        assignee_ids: Optional[List[uuid.UUID]] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        created_on: Optional[date] = None,
        due_on: Optional[date] = None,
        due_from: Optional[date] = None,
        due_to: Optional[date] = None,
        labels: Optional[List[str]] = None,
        scope: Optional[str] = None,
        deleted_only: bool = False,
        filter_operator: str = "and",
    ) -> Tuple[List[Task], int]:
        return self.repository.get_all(
            skip=skip,
            limit=limit,
            search=search,
            assignee_ids=assignee_ids,
            priority=priority,
            status=status,
            created_on=created_on,
            due_on=due_on,
            due_from=due_from,
            due_to=due_to,
            labels=labels,
            scope=scope,
            deleted_only=deleted_only,
            filter_operator=filter_operator,
        )

    def get_dashboard(self, *, aad_object_id: Optional[str], email: Optional[str]) -> TaskDashboardResponse:
        """open_tasks is scoped to the current user's own open tasks; every other field stays
        a global aggregate. Same identity resolution order as get_notifications_for_user."""
        user = None
        if aad_object_id:
            user = self.user_repository.get_by_aad_object_id(aad_object_id)
        if user is None and email:
            user = self.user_repository.get_by_email(email)

        if user is None:
            logger.warning(
                "No user found for dashboard open_tasks scoping: aad_object_id=%s email=%s",
                aad_object_id,
                email,
            )
        return self.repository.get_dashboard_stats(user_id=user.id if user is not None else None)

    def get_user_stats(self) -> List[UserTaskStatsResponse]:
        return self.repository.get_stats_by_user()

    def get_task_history(self, task_id: uuid.UUID) -> List[TaskChangeHistory]:
        self.get_task(task_id)
        return self.history_repository.list_for_task(task_id)

    def get_task_labels(self, task_id: uuid.UUID) -> List[Label]:
        task = self.get_task(task_id)
        return task.labels

    @staticmethod
    def _label_names(task: Task) -> List[str]:
        return sorted(label.name for label in task.labels)

    def attach_label(
        self,
        task_id: uuid.UUID,
        label_id: uuid.UUID,
        *,
        actor_oid: Optional[str] = None,
    ) -> Label:
        task = self.get_task(task_id)
        label = self.label_repository.get_by_id(label_id)
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        before = self._label_names(task)
        self.repository.attach_label(task, label)
        after = self._label_names(task)
        if after != before:
            self.history_repository.record(
                task=task,
                field_name="labels",
                old_value=before,
                new_value=after,
                source="api",
                updated_by=self._resolve_updated_by(actor_oid),
            )
        return label

    def detach_label(
        self,
        task_id: uuid.UUID,
        label_id: uuid.UUID,
        *,
        actor_oid: Optional[str] = None,
    ) -> None:
        task = self.get_task(task_id)
        label = self.label_repository.get_by_id(label_id)
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        before = self._label_names(task)
        self.repository.detach_label(task, label)
        after = self._label_names(task)
        if after != before:
            self.history_repository.record(
                task=task,
                field_name="labels",
                old_value=before,
                new_value=after,
                source="api",
                updated_by=self._resolve_updated_by(actor_oid),
            )

    def get_notifications_for_user(
        self,
        *,
        aad_object_id: Optional[str],
        email: Optional[str],
        page: int = 1,
        page_size: int = 20,
        source: Optional[str] = None,
    ) -> TaskNotificationPage:
        """Cross-task notification feed: every task_change_notification row addressed to the
        given identity, most recent first. aad_object_id is tried first (set once a user has
        interacted with the Teams bot); email is the fallback for a user known only via SSO.
        source, when given, filters to notifications whose underlying history row was recorded
        with that task_change_history.source (e.g. "api", "email_analysis", "teams_bot")."""
        user = None
        if aad_object_id:
            user = self.user_repository.get_by_aad_object_id(aad_object_id)
        if user is None and email:
            user = self.user_repository.get_by_email(email)

        if user is None:
            logger.warning(
                "No user found for notification feed: aad_object_id=%s email=%s",
                aad_object_id,
                email
            )
            return TaskNotificationPage(items=[], total=0, page=page, page_size=page_size)

        skip = (page - 1) * page_size
        rows, total = self.notification_repository.list_and_count_for_user(
            user.id, skip=skip, limit=page_size, source=source
        )
        items = [
            TaskNotificationResponse(
                id=notification.id,
                created_at=notification.created_at,
                task_change_history=TaskChangeHistoryDetail(
                    id=history.id,
                    field_name=history.field_name,
                    old_value=history.old_value,
                    new_value=history.new_value,
                    source=history.source,
                    updated_by=UserResponse.model_validate(updated_by_user) if updated_by_user is not None else None,
                    processed_email_id=history.processed_email_id,
                    changed_at=history.changed_at,
                    task=TaskResponse.model_validate(task),
                ),
            )
            for notification, history, task, updated_by_user in rows
        ]
        return TaskNotificationPage(items=items, total=total, page=page, page_size=page_size)

    @staticmethod
    def _snapshot_field(task: Task, field: str) -> Any:
        if field == "due_date":
            return task.due_date.isoformat() if task.due_date else None
        if field == "assignee_ids":
            # Raw user ids, matching what this field actually is everywhere else in the
            # schema (Task.assignee_ids) — not emails, to avoid duplicating PII into the
            # audit table and to stay consistent if a user's email is later changed.
            return sorted(str(user.id) for user in task.assignees)
        return getattr(task, field)

    def update_task(
        self,
        task_id: uuid.UUID,
        task_data: TaskUpdate,
        *,
        source: str = "api",
        actor_oid: Optional[str] = None,
        processed_email_id: Optional[uuid.UUID] = None,
    ) -> Task:
        task = self.get_task(task_id)
        self._validate_assignees(task_data.assignee_ids)

        # Snapshot every tracked field the caller is actually touching BEFORE the repository
        # mutates `task` in place (TaskRepository.update sets attributes on the same object
        # it's given, so capturing "before" values has to happen first).
        tracked_fields = task_data.model_fields_set & _TRACKED_FIELDS
        before = {field: self._snapshot_field(task, field) for field in tracked_fields}

        updated = self.repository.update(task, task_data)

        updated_by = self._resolve_updated_by(actor_oid)
        for field in tracked_fields:
            after = self._snapshot_field(updated, field)
            if after != before[field]:
                self.history_repository.record(
                    task=updated,
                    field_name=field,
                    old_value=before[field],
                    new_value=after,
                    source=source,
                    updated_by=updated_by,
                    processed_email_id=processed_email_id,
                )
        return updated

    def delete_task(
        self,
        task_id: uuid.UUID,
        *,
        actor_oid: Optional[str] = None,
    ) -> None:
        task = self.get_task(task_id)
        self.repository.soft_delete(task)
        self.history_repository.record(
            task=task,
            field_name="deleted_at",
            old_value=None,
            new_value=task.deleted_at.isoformat() if task.deleted_at else None,
            source="api",
            updated_by=self._resolve_updated_by(actor_oid),
        )

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
        processed_email_id: Optional[uuid.UUID] = None,
    ) -> Optional[Task]:
        seed_conversation_ids = list(thread_conversation_ids or [])
        if metadata.conversation_id:
            seed_conversation_ids.append(metadata.conversation_id)

        if analysis.action == ActionType.IGNORE:
            return None

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
            return await self.create_task(
                task_data, source="email_analysis", processed_email_id=processed_email_id
            )

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
                assignee_ids = self._resolve_assignee_ids(analysis.payload.assignees)
                if assignee_ids:
                    update_data["assignee_ids"] = assignee_ids
            update_data["conversation_ids"] = self._merged_conversation_ids(
                task,
                conversation_ids=seed_conversation_ids,
            )
            return self.update_task(
                task.id,
                TaskUpdate(**update_data),
                source="email_analysis",
                processed_email_id=processed_email_id,
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
