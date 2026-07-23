import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_notification import TaskNotification


class TaskNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_for_assignees(
        self,
        task: Task,
        *,
        notification_type: str,
        origin_type: str,
        origin_id: Optional[uuid.UUID],
    ) -> List[TaskNotification]:
        entries = [
            TaskNotification(
                task_id=task.id,
                type=notification_type,
                user_id=assignee.id,
                origin_type=origin_type,
                origin_id=origin_id,
            )
            for assignee in task.assignees
        ]
        if not entries:
            return []
        self.db.add_all(entries)
        self.db.commit()
        for entry in entries:
            self.db.refresh(entry)
        return entries
