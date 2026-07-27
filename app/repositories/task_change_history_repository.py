import uuid
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_change_history import TaskChangeHistory
from app.repositories.task_change_notification_repository import TaskChangeNotificationRepository


class TaskChangeHistoryRepository:
    def __init__(self, db: Session):
        self.db = db
        self.notification_repository = TaskChangeNotificationRepository(db)

    def record(
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
        return entry

    def list_for_task(self, task_id: uuid.UUID) -> List[TaskChangeHistory]:
        return (
            self.db.query(TaskChangeHistory)
            .filter(TaskChangeHistory.task_id == task_id)
            .order_by(TaskChangeHistory.changed_at.asc())
            .all()
        )
