import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.teams_auth import get_current_teams_user
from app.database import get_db
from app.repositories.label_repository import LabelRepository
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate
from app.services.label_service import LabelService

router = APIRouter(prefix="/labels", tags=["labels"], dependencies=[Depends(get_current_teams_user)])


def get_label_service(db: Session = Depends(get_db)) -> LabelService:
    return LabelService(LabelRepository(db))


@router.post("", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
def create_label(label_data: LabelCreate, service: LabelService = Depends(get_label_service)):
    return service.create_label(label_data)


@router.get("", response_model=List[LabelResponse])
def list_labels(service: LabelService = Depends(get_label_service)):
    return service.list_labels()


@router.get("/{label_id}", response_model=LabelResponse)
def get_label(label_id: uuid.UUID, service: LabelService = Depends(get_label_service)):
    return service.get_label(label_id)


@router.put("/{label_id}", response_model=LabelResponse)
def update_label(label_id: uuid.UUID, label_data: LabelUpdate, service: LabelService = Depends(get_label_service)):
    return service.update_label(label_id, label_data)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(label_id: uuid.UUID, service: LabelService = Depends(get_label_service)):
    service.delete_label(label_id)
