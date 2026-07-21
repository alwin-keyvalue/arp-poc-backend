import uuid
from datetime import date
from typing import List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate

_TASK_METADATA_FIELDS = {"conversation_ids", "internet_message_ids"}
# created_via lives in metadata_ too, but unlike the fields above it's create-only (not on
# TaskUpdate at all) — excluded here just so the flat model_dump().setattr loop in create()
# doesn't try to pass it to Task(**data), which has no matching column.
_TASK_EXCLUDED_FIELDS = _TASK_METADATA_FIELDS | {"assignee_ids", "created_via"}


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_users(self, user_ids: Sequence[uuid.UUID]) -> List[User]:
        if not user_ids:
            return []
        return self.db.query(User).filter(User.id.in_(user_ids), User.is_deleted.is_(False)).all()

    @staticmethod
    def _dedupe(values: Sequence[str]) -> List[str]:
        return list(dict.fromkeys(values))

    def create(self, task_data: TaskCreate) -> Task:
        data = task_data.model_dump(exclude=_TASK_EXCLUDED_FIELDS)
        task = Task(**data)
        task.assignees = self._resolve_users(task_data.assignee_ids)
        task.metadata_ = {
            "conversation_ids": self._dedupe(task_data.conversation_ids),
            "internet_message_ids": self._dedupe(task_data.internet_message_ids),
            "created_via": task_data.created_via,
        }
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, task_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[Task]:
        query = self.db.query(Task).options(selectinload(Task.assignees)).filter(Task.id == task_id)
        if not include_deleted:
            query = query.filter(Task.is_deleted.is_(False))
        return query.first()

    def get_by_conversation_id(self, conversation_id: str) -> Optional[Task]:
        return (
            self.db.query(Task)
            .filter(
                Task.metadata_.contains({"conversation_ids": [conversation_id]}),
                Task.is_deleted.is_(False),
            )
            .order_by(Task.last_update.desc())
            .first()
        )

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        return (
            self.db.query(Task)
            .options(selectinload(Task.assignees))
            .filter(Task.is_deleted.is_(False))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, task: Task, task_data: TaskUpdate) -> Task:
        for field, value in task_data.model_dump(exclude_unset=True, exclude=_TASK_EXCLUDED_FIELDS).items():
            setattr(task, field, value)
        if "assignee_ids" in task_data.model_fields_set:
            task.assignees = self._resolve_users(task_data.assignee_ids or [])
        fields_set = task_data.model_fields_set
        if _TASK_METADATA_FIELDS & fields_set:
            # Reassign a new dict (rather than mutate in place) so SQLAlchemy detects the change
            # without needing sqlalchemy.ext.mutable.MutableDict.
            metadata = dict(task.metadata_ or {})
            if "conversation_ids" in fields_set:
                metadata["conversation_ids"] = self._dedupe(task_data.conversation_ids or [])
            if "internet_message_ids" in fields_set:
                metadata["internet_message_ids"] = self._dedupe(task_data.internet_message_ids or [])
            task.metadata_ = metadata
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
            .options(selectinload(Task.assignees))
            .filter(Task.is_deleted.is_(False))
            .filter(func.date(Task.created_at) >= from_date, func.date(Task.created_at) <= to_date)
            .order_by(Task.created_at.asc())
            .all()
        )
