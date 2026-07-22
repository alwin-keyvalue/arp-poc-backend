import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.teams_auth import TeamsUser, get_current_teams_user
from app.database import get_db
from app.repositories.note_repository import NoteRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate
from app.services.note_service import NoteService

router = APIRouter(prefix="/tasks/{task_id}/notes", tags=["notes"], dependencies=[Depends(get_current_teams_user)])


def get_note_service(db: Session = Depends(get_db)) -> NoteService:
    return NoteService(NoteRepository(db), TaskRepository(db))


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    task_id: uuid.UUID,
    note_data: NoteCreate,
    service: NoteService = Depends(get_note_service),
    actor: TeamsUser = Depends(get_current_teams_user),
):
    return service.create_note(task_id, note_data, created_by=actor.display_label)


@router.get("", response_model=List[NoteResponse])
def list_notes(task_id: uuid.UUID, service: NoteService = Depends(get_note_service)):
    return service.list_notes(task_id)


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(task_id: uuid.UUID, note_id: uuid.UUID, service: NoteService = Depends(get_note_service)):
    return service.get_note(task_id, note_id)


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    task_id: uuid.UUID,
    note_id: uuid.UUID,
    note_data: NoteUpdate,
    service: NoteService = Depends(get_note_service),
):
    return service.update_note(task_id, note_id, note_data)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(task_id: uuid.UUID, note_id: uuid.UUID, service: NoteService = Depends(get_note_service)):
    service.delete_note(task_id, note_id)
