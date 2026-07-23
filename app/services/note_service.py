import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.models.task_note import TaskNote
from app.repositories.note_repository import NoteRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.note import NoteCreate, NoteUpdate

logger = logging.getLogger(__name__)


class NoteService:
    def __init__(
        self,
        repository: NoteRepository,
        task_repository: TaskRepository,
        user_repository: UserRepository,
    ):
        self.repository = repository
        self.task_repository = task_repository
        self.user_repository = user_repository

    def _get_task_or_404(self, task_id: uuid.UUID) -> None:
        if self.task_repository.get_by_id(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    def _resolve_actor_id(self, *, aad_object_id: Optional[str], email: Optional[str]) -> Optional[uuid.UUID]:
        """Same resolution order as get_activity_for_user / get_current_user: aad_object_id
        first (set once a user has interacted with the Teams bot), email as the SSO fallback."""
        user = None
        if aad_object_id:
            user = self.user_repository.get_by_aad_object_id(aad_object_id)
        if user is None and email:
            user = self.user_repository.get_by_email(email)
        if user is None:
            logger.warning(
                "Could not resolve note author to a known user: aad_object_id=%s email=%s",
                aad_object_id,
                email,
            )
            return None
        return user.id

    def create_note(
        self,
        task_id: uuid.UUID,
        data: NoteCreate,
        *,
        aad_object_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> TaskNote:
        self._get_task_or_404(task_id)
        created_by = self._resolve_actor_id(aad_object_id=aad_object_id, email=email)
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

    def _ensure_owner(
        self, note: TaskNote, *, aad_object_id: Optional[str], email: Optional[str], action: str
    ) -> None:
        actor_id = self._resolve_actor_id(aad_object_id=aad_object_id, email=email)
        if actor_id is None or note.created_by != actor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Only the note's author can {action} it"
            )

    def update_note(
        self,
        task_id: uuid.UUID,
        note_id: uuid.UUID,
        data: NoteUpdate,
        *,
        aad_object_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> TaskNote:
        note = self.get_note(task_id, note_id)
        self._ensure_owner(note, aad_object_id=aad_object_id, email=email, action="edit")
        return self.repository.update(note, data)

    def delete_note(
        self,
        task_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        aad_object_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> None:
        note = self.get_note(task_id, note_id)
        self._ensure_owner(note, aad_object_id=aad_object_id, email=email, action="delete")
        self.repository.soft_delete(note)
