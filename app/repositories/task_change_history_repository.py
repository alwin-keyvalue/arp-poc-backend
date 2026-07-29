import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_change_history import TaskChangeHistory
from app.repositories.task_change_notification_repository import TaskChangeNotificationRepository

if TYPE_CHECKING:
    # Deferred to avoid a circular import: bot_service.py itself imports this module.
    from app.services.bot_service import BotService

# Which field_name values should also ping the affected assignees via Teams DM, on top of
# the task_change_notification row every field change already gets. "status" only counts
# when old_value is None (i.e. the row create_task writes for a brand-new task, not a later
# status transition); "assignee_ids" always counts, but only notifies the assignees newly
# added by that change; "due_date"/"priority" always notify every current assignee.
_ASSIGNMENT_NOTIFY_FIELDS = {"status", "assignee_ids", "due_date", "priority"}

_ASSIGNED_HEADING = "📌 New task assigned"
# Headings for the fields that notify without being an assignment change.
_FIELD_UPDATE_HEADINGS = {
    "due_date": "📅 Due date updated",
    "priority": "⚠️ Priority updated",
}


class TaskChangeHistoryRepository:
    def __init__(self, db: Session, bot_service: "BotService"):
        self.db = db
        self.notification_repository = TaskChangeNotificationRepository(db)
        self.bot_service = bot_service

    async def record(
        self,
        *,
        task: Task,
        field_name: str,
        old_value: Any,
        new_value: Any,
        source: str,
        updated_by: Optional[uuid.UUID] = None,
        processed_email_id: Optional[uuid.UUID] = None,
    ) -> TaskChangeHistory:
        entry = TaskChangeHistory(
            task_id=task.id,
            task_title=task.title,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            source=source,
            updated_by=updated_by,
            processed_email_id=processed_email_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        # Every history row notifies the task's current assignees, regardless of caller
        # (API, webhook/email analysis, or Teams bot) — see TaskService/BotService callers.
        self.notification_repository.create_for_history(entry, task.assignees)
        await self._notify_assignees_if_relevant(task, field_name, old_value)
        return entry

    async def _notify_assignees_if_relevant(self, task: Task, field_name: str, old_value: Any) -> None:
        if field_name not in _ASSIGNMENT_NOTIFY_FIELDS:
            return

        heading = _ASSIGNED_HEADING
        if field_name == "status":
            if old_value is not None:
                return  # a real status transition, not the initial creation row
            assignees_to_notify = task.assignees
        elif field_name == "assignee_ids":
            previous_ids = set(old_value or [])
            assignees_to_notify = [a for a in task.assignees if str(a.id) not in previous_ids]
        else:
            heading = _FIELD_UPDATE_HEADINGS[field_name]
            assignees_to_notify = task.assignees

        for assignee in assignees_to_notify:
            await self.bot_service.notify_task_assigned(assignee, task, heading=heading)

    def list_for_task(self, task_id: uuid.UUID) -> List[TaskChangeHistory]:
        return (
            self.db.query(TaskChangeHistory)
            .filter(TaskChangeHistory.task_id == task_id)
            .order_by(TaskChangeHistory.changed_at.asc())
            .all()
        )
