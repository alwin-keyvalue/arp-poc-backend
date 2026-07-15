import uuid
from datetime import date
from typing import List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_users(self, user_ids: Sequence[uuid.UUID]) -> List[User]:
        if not user_ids:
            return []
        return self.db.query(User).filter(User.id.in_(user_ids)).all()

    def create(self, task_data: TaskCreate) -> Task:
        data = task_data.model_dump(exclude={"assignee_ids"})
        task = Task(**data)
        task.assignees = self._resolve_users(task_data.assignee_ids)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, task_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[Task]:
        query = self.db.query(Task).filter(Task.id == task_id)
        if not include_deleted:
            query = query.filter(Task.is_deleted.is_(False))
        return query.first()

    def get_by_conversation_id(self, conversation_id: str) -> Optional[Task]:
        return (
            self.db.query(Task)
            .filter(Task.conversation_id == conversation_id, Task.is_deleted.is_(False))
            .order_by(Task.last_update.desc())
            .first()
        )

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        return (
            self.db.query(Task)
            .filter(Task.is_deleted.is_(False))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, task: Task, task_data: TaskUpdate) -> Task:
        for field, value in task_data.model_dump(exclude_unset=True, exclude={"assignee_ids"}).items():
            setattr(task, field, value)
        if "assignee_ids" in task_data.model_fields_set:
            task.assignees = self._resolve_users(task_data.assignee_ids or [])
        self.db.commit()
        self.db.refresh(task)
        return task

    def soft_delete(self, task: Task) -> None:
        task.is_deleted = True
        self.db.commit()
        self.db.refresh(task)

    def get_created_between(self, from_date: date, to_date: date) -> List[Task]:
        return (
            self.db.query(Task)
            .filter(Task.is_deleted.is_(False))
            .filter(func.date(Task.created_at) >= from_date, func.date(Task.created_at) <= to_date)
            .order_by(Task.created_at.asc())
            .all()
        )
