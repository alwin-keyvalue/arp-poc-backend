import uuid
from typing import Any, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_assignee import TaskAssignee
from app.models.task_change_history import TaskChangeHistory


class TaskChangeHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        task: Task,
        field_name: str,
        old_value: Any,
        new_value: Any,
        source: str,
        changed_by_oid: Optional[str] = None,
        changed_by_name: Optional[str] = None,
    ) -> TaskChangeHistory:
        entry = TaskChangeHistory(
            task_id=task.id,
            task_title=task.title,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            source=source,
            changed_by_oid=changed_by_oid,
            changed_by_name=changed_by_name,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_for_task(self, task_id: uuid.UUID) -> List[TaskChangeHistory]:
        return (
            self.db.query(TaskChangeHistory)
            .filter(TaskChangeHistory.task_id == task_id)
            .order_by(TaskChangeHistory.changed_at.asc())
            .all()
        )

    def _for_assignee_query(self, user_id: uuid.UUID):
        return (
            self.db.query(TaskChangeHistory)
            .join(Task, TaskChangeHistory.task_id == Task.id)
            .join(TaskAssignee, TaskAssignee.task_id == Task.id)
            .filter(TaskAssignee.user_id == user_id, Task.is_deleted.is_(False))
        )

    def list_and_count_for_assignee(
        self, user_id: uuid.UUID, *, skip: int = 0, limit: int = 20
    ) -> Tuple[List[TaskChangeHistory], int]:
        base_query = self._for_assignee_query(user_id)
        total = base_query.with_entities(func.count(func.distinct(TaskChangeHistory.id))).scalar() or 0
        items = (
            base_query.order_by(TaskChangeHistory.changed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total
