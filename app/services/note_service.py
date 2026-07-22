import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.models.task_note import TaskNote
from app.repositories.note_repository import NoteRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.note import NoteCreate, NoteUpdate


class NoteService:
    def __init__(self, repository: NoteRepository, task_repository: TaskRepository):
        self.repository = repository
        self.task_repository = task_repository

    def _get_task_or_404(self, task_id: uuid.UUID) -> None:
        if self.task_repository.get_by_id(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    def create_note(self, task_id: uuid.UUID, data: NoteCreate, *, created_by: Optional[str] = None) -> TaskNote:
        self._get_task_or_404(task_id)
        return self.repository.create(task_id, data, created_by=created_by)

    def list_notes(self, task_id: uuid.UUID) -> List[TaskNote]:
        self._get_task_or_404(task_id)
        return self.repository.list_for_task(task_id)

    def get_note(self, task_id: uuid.UUID, note_id: uuid.UUID) -> TaskNote:
        self._get_task_or_404(task_id)
        note = self.repository.get_by_id(note_id)
        if note is None or note.task_id != task_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
        return note

    def update_note(self, task_id: uuid.UUID, note_id: uuid.UUID, data: NoteUpdate) -> TaskNote:
        note = self.get_note(task_id, note_id)
        return self.repository.update(note, data)

    def delete_note(self, task_id: uuid.UUID, note_id: uuid.UUID) -> None:
        note = self.get_note(task_id, note_id)
        self.repository.soft_delete(note)
