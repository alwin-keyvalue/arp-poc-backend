import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_status_history import TaskStatusHistory


class TaskStatusHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        task: Task,
        from_status: Optional[str],
        to_status: str,
        source: str,
        changed_by_oid: Optional[str] = None,
        changed_by_name: Optional[str] = None,
    ) -> TaskStatusHistory:
        entry = TaskStatusHistory(
            task_id=task.id,
            task_title=task.title,
            from_status=from_status,
            to_status=to_status,
            source=source,
            changed_by_oid=changed_by_oid,
            changed_by_name=changed_by_name,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_for_task(self, task_id: uuid.UUID) -> List[TaskStatusHistory]:
        return (
            self.db.query(TaskStatusHistory)
            .filter(TaskStatusHistory.task_id == task_id)
            .order_by(TaskStatusHistory.changed_at.asc())
            .all()
        )
