import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.label import Label
from app.models.task_label import TaskLabel
from app.schemas.label import LabelCreate, LabelUpdate


class LabelRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: LabelCreate) -> Label:
        label = Label(name=data.name.strip())
        self.db.add(label)
        self.db.commit()
        self.db.refresh(label)
        return label

    def get_by_id(self, label_id: uuid.UUID) -> Optional[Label]:
        return self.db.query(Label).filter(Label.id == label_id).first()

    def get_by_name(self, name: str) -> Optional[Label]:
        return self.db.query(Label).filter(Label.name == name.strip()).first()

    def get_all(self) -> List[Label]:
        return self.db.query(Label).order_by(Label.name).all()

    def update(self, label: Label, data: LabelUpdate) -> Label:
        if data.name is not None:
            label.name = data.name.strip()
        self.db.commit()
        self.db.refresh(label)
        return label

    def delete(self, label: Label) -> None:
        # Labels are hard-deleted (unlike tasks/users), so the join rows have to be cleaned up
        # explicitly here rather than relying on an ON DELETE CASCADE the rest of this codebase
        # doesn't otherwise use.
        self.db.query(TaskLabel).filter(TaskLabel.label_id == label.id).delete()
        self.db.delete(label)
        self.db.commit()
