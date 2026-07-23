import uuid
from datetime import date, timedelta
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import String, and_, case, cast, func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.label import Label
from app.models.task import Task, TaskStatus
from app.models.task_assignee import TaskAssignee
from app.models.user import User
from app.schemas.task import TaskCreate, TaskDashboardResponse, TaskUpdate, UserTaskStatsResponse

_CLOSED_STATUSES = (TaskStatus.DONE.value, TaskStatus.DROPPED.value)

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
        query = (
            self.db.query(Task)
            .options(selectinload(Task.assignees), selectinload(Task.labels))
            .filter(Task.id == task_id)
        )
        if not include_deleted:
            query = query.filter(Task.deleted_at.is_(None))
        return query.first()

    def attach_label(self, task: Task, label: Label) -> Task:
        if label not in task.labels:
            task.labels.append(label)
            self.db.commit()
            self.db.refresh(task)
        return task

    def detach_label(self, task: Task, label: Label) -> Task:
        if label in task.labels:
            task.labels.remove(label)
            self.db.commit()
            self.db.refresh(task)
        return task

    def get_by_conversation_id(self, conversation_id: str) -> Optional[Task]:
        return (
            self.db.query(Task)
            .filter(
                Task.metadata_.contains({"conversation_ids": [conversation_id]}),
                Task.deleted_at.is_(None),
            )
            .order_by(Task.last_update.desc())
            .first()
        )

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        *,
        search: Optional[str] = None,
        assignee_id: Optional[uuid.UUID] = None,
        priority: Optional[str] = None,
        created_on: Optional[date] = None,
        due_on: Optional[date] = None,
        due_from: Optional[date] = None,
        due_to: Optional[date] = None,
        label: Optional[str] = None,
        scope: Optional[str] = None,
        deleted_only: bool = False,
    ) -> Tuple[List[Task], int]:
        deleted_filter = Task.deleted_at.isnot(None) if deleted_only else Task.deleted_at.is_(None)
        query = self.db.query(Task).filter(deleted_filter)

        if search and (term := search.strip()):
            pattern = f"%{term}%"
            query = query.filter(
                or_(
                    Task.title.ilike(pattern),
                    Task.description.ilike(pattern),
                )
            )

        if assignee_id is not None:
            query = query.filter(Task.assignees.any(User.id == assignee_id))

        if priority is not None:
            query = query.filter(Task.priority == priority)

        if created_on is not None:
            query = query.filter(func.date(Task.created_at) == created_on)

        if due_on is not None:
            query = query.filter(Task.due_date == due_on)

        if due_from is not None:
            query = query.filter(Task.due_date.isnot(None), Task.due_date >= due_from)

        if due_to is not None:
            query = query.filter(Task.due_date.isnot(None), Task.due_date <= due_to)

        if label and (tag := label.strip()):
            # labels is a JSON array of strings — match a quoted element in the serialized value.
            query = query.filter(cast(Task.labels, String).like(f'%"{tag}"%'))

        if scope is not None:
            query = self._apply_scope_filter(query, scope)

        total = query.count()
        items = (
            query.options(selectinload(Task.assignees), selectinload(Task.labels))
            .order_by(Task.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def _apply_scope_filter(query, scope: str, *, today: Optional[date] = None):
        """Align list filtering with get_dashboard_stats buckets."""
        today = today or date.today()
        week_end = today + timedelta(days=7)
        is_open = Task.status.notin_(_CLOSED_STATUSES)

        if scope == "open":
            return query.filter(is_open)
        if scope == "overdue":
            return query.filter(is_open, Task.due_date.isnot(None), Task.due_date < today)
        if scope == "due_this_week":
            return query.filter(
                is_open,
                Task.due_date.isnot(None),
                Task.due_date >= today,
                Task.due_date <= week_end,
            )
        if scope == "completed":
            return query.filter(Task.status == TaskStatus.DONE.value)
        return query

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
        task.deleted_at = func.now()
        self.db.commit()
        self.db.refresh(task)

    def get_created_between(self, from_date: date, to_date: date) -> List[Task]:
        return (
            self.db.query(Task)
            .options(selectinload(Task.assignees))
            .filter(Task.deleted_at.is_(None))
            .filter(func.date(Task.created_at) >= from_date, func.date(Task.created_at) <= to_date)
            .order_by(Task.created_at.asc())
            .all()
        )

    def get_stats_by_user(self, *, today: Optional[date] = None) -> List[UserTaskStatsResponse]:
        """Same open/overdue/due_this_week/completed buckets as get_dashboard_stats, grouped
        per assignee instead of across all tasks. LEFT JOINs so every non-deleted user is
        included (all-zero counts) even with no tasks assigned; a task with multiple
        assignees counts toward each of them."""
        today = today or date.today()
        week_end = today + timedelta(days=7)
        is_open = Task.status.notin_(_CLOSED_STATUSES)

        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.email.label("email"),
                User.display_name.label("display_name"),
                func.coalesce(func.sum(case((is_open, 1), else_=0)), 0).label("open_tasks"),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(is_open, Task.due_date.isnot(None), Task.due_date < today), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("overdue"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    is_open,
                                    Task.due_date.isnot(None),
                                    Task.due_date >= today,
                                    Task.due_date <= week_end,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("due_this_week"),
                func.coalesce(
                    func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
                    0,
                ).label("completed"),
            )
            .select_from(User)
            .outerjoin(TaskAssignee, TaskAssignee.user_id == User.id)
            .outerjoin(Task, and_(Task.id == TaskAssignee.task_id, Task.deleted_at.is_(None)))
            .filter(User.is_deleted.is_(False))
            .group_by(User.id, User.email, User.display_name)
            .order_by(User.email)
            .all()
        )

        return [
            UserTaskStatsResponse(
                user_id=row.user_id,
                email=row.email,
                display_name=row.display_name,
                open_tasks=int(row.open_tasks or 0),
                overdue=int(row.overdue or 0),
                due_this_week=int(row.due_this_week or 0),
                completed=int(row.completed or 0),
            )
            for row in rows
        ]

    def get_dashboard_stats(self, *, today: Optional[date] = None) -> TaskDashboardResponse:
        today = today or date.today()
        week_end = today + timedelta(days=7)
        is_open = Task.status.notin_(_CLOSED_STATUSES)

        row = (
            self.db.query(
                func.count(Task.id).label("total"),
                func.coalesce(func.sum(case((is_open, 1), else_=0)), 0).label("open_tasks"),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(is_open, Task.due_date.isnot(None), Task.due_date < today), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("overdue"),
                func.coalesce(
                    func.sum(case((and_(is_open, Task.due_date == today), 1), else_=0)),
                    0,
                ).label("due_today"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    is_open,
                                    Task.due_date.isnot(None),
                                    Task.due_date >= today,
                                    Task.due_date <= week_end,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("due_this_week"),
                func.coalesce(
                    func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
                    0,
                ).label("done"),
            )
            .filter(Task.deleted_at.is_(None))
            .one()
        )

        total = int(row.total or 0)
        done = int(row.done or 0)
        return TaskDashboardResponse(
            open_tasks=int(row.open_tasks or 0),
            total=total,
            overdue=int(row.overdue or 0),
            due_today=int(row.due_today or 0),
            due_this_week=int(row.due_this_week or 0),
            completed_pct=round((done / total) * 100) if total else 0,
        )
