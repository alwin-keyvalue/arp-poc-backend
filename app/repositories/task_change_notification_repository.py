import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_change_history import TaskChangeHistory
from app.models.task_change_notification import TaskChangeNotification
from app.models.user import User

# The row shape returned by list_and_count_for_user: the notification itself, its history
# entry, the task the history row belongs to, and the user who made the change (None for
# email/webhook-triggered changes, which have no acting user).
NotificationRow = Tuple[TaskChangeNotification, TaskChangeHistory, Task, Optional[User]]


class TaskChangeNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_for_history(
        self, history_entry: TaskChangeHistory, assignees: Sequence[User]
    ) -> List[TaskChangeNotification]:
        entries = [
            TaskChangeNotification(task_change_history_id=history_entry.id, user_id=assignee.id)
            for assignee in assignees
        ]
        if not entries:
            return []
        self.db.add_all(entries)
        self.db.commit()
        for entry in entries:
            self.db.refresh(entry)
        return entries

    def _for_user_query(self, user_id: uuid.UUID, *, source: Optional[str] = None):
        query = (
            self.db.query(TaskChangeNotification, TaskChangeHistory, Task, User)
            .join(TaskChangeHistory, TaskChangeNotification.task_change_history_id == TaskChangeHistory.id)
            .join(Task, TaskChangeHistory.task_id == Task.id)
            .outerjoin(User, TaskChangeHistory.updated_by == User.id)
            .filter(TaskChangeNotification.user_id == user_id)
        )
        if source is not None:
            query = query.filter(TaskChangeHistory.source == source)
        return query

    def list_and_count_for_user(
        self, user_id: uuid.UUID, *, skip: int = 0, limit: int = 20, source: Optional[str] = None
    ) -> Tuple[List[NotificationRow], int]:
        base_query = self._for_user_query(user_id, source=source)

        # Single round trip: fold the total into the same result set via a window function
        # instead of a separate COUNT(*) query. Only falls back to a real COUNT query for the
        # edge case of an empty page (skip past the end) — a window function has no row to
        # carry the total on when the page itself comes back empty.
        rows = (
            base_query.add_columns(func.count().over().label("total_count"))
            .order_by(TaskChangeNotification.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        if rows:
            items = [row[:4] for row in rows]
            total = rows[0][4]
            return items, total

        total = base_query.with_entities(func.count(func.distinct(TaskChangeNotification.id))).scalar() or 0
        return [], total
