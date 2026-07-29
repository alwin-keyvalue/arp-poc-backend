"""soft delete tasks and fk task status history

Revision ID: ac396c71d18f
Revises: fa1335b44ab6
Create Date: 2026-07-14 13:41:03.722473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac396c71d18f'
down_revision: Union[str, Sequence[str], None] = 'fa1335b44ab6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        "fk_task_status_history_task_id", "task_status_history", "tasks", ["task_id"], ["id"]
    )
    op.add_column('tasks', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'is_deleted')
    op.drop_constraint("fk_task_status_history_task_id", "task_status_history", type_='foreignkey')
