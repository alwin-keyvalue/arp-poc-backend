import uuid

from fastapi import HTTPException, status

from app.models.label import Label
from app.repositories.label_repository import LabelRepository
from app.schemas.label import LabelCreate, LabelUpdate


class LabelService:
    def __init__(self, repository: LabelRepository):
        self.repository = repository

    def create_label(self, data: LabelCreate) -> Label:
        existing = self.repository.get_by_name(data.name)
        if existing:
            return existing
        return self.repository.create(data)

    def list_labels(self) -> list[Label]:
        return self.repository.get_all()

    def get_label(self, label_id: uuid.UUID) -> Label:
        label = self.repository.get_by_id(label_id)
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        return label

    def update_label(self, label_id: uuid.UUID, data: LabelUpdate) -> Label:
        label = self.get_label(label_id)
        if data.name is not None and data.name.strip() != label.name:
            existing = self.repository.get_by_name(data.name)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=f"Label '{data.name}' already exists"
                )
        return self.repository.update(label, data)

    def delete_label(self, label_id: uuid.UUID) -> None:
        label = self.get_label(label_id)
        self.repository.delete(label)
