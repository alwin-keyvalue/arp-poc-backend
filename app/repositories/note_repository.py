import uuid
from typing import List, Optional

from sqlalchemy.sql import func
from sqlalchemy.orm import Session, selectinload

from app.models.task_note import TaskNote
from app.schemas.note import NoteCreate, NoteUpdate


class NoteRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, task_id: uuid.UUID, data: NoteCreate, *, created_by: Optional[uuid.UUID] = None) -> TaskNote:
        note = TaskNote(task_id=task_id, description=data.description, created_by=created_by)
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def get_by_id(self, note_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[TaskNote]:
        query = self.db.query(TaskNote).options(selectinload(TaskNote.creator)).filter(TaskNote.id == note_id)
        if not include_deleted:
            query = query.filter(TaskNote.deleted_at.is_(None))
        return query.first()

    def list_for_task(self, task_id: uuid.UUID, *, include_deleted: bool = False) -> List[TaskNote]:
        query = (
            self.db.query(TaskNote)
            .options(selectinload(TaskNote.creator))
            .filter(TaskNote.task_id == task_id)
        )
        if not include_deleted:
            query = query.filter(TaskNote.deleted_at.is_(None))
        return query.order_by(TaskNote.created_at.asc()).all()

    def update(self, note: TaskNote, data: NoteUpdate) -> TaskNote:
        note.description = data.description
        self.db.commit()
        self.db.refresh(note)
        return note

    def soft_delete(self, note: TaskNote) -> None:
        note.deleted_at = func.now()
        self.db.commit()
        self.db.refresh(note)
