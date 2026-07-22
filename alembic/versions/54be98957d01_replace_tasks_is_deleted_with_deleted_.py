"""replace tasks.is_deleted with deleted_at timestamp

Revision ID: 54be98957d01
Revises: 552c0893308f
Create Date: 2026-07-22 12:35:24.083718

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54be98957d01'
down_revision: Union[str, Sequence[str], None] = '552c0893308f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Best-effort backfill: the old boolean never recorded *when* a task was deleted, and
    # last_update's onupdate=func.now() means it was bumped to the deletion time by
    # soft_delete()'s own UPDATE — the closest proxy we have to an actual deleted_at.
    op.execute("UPDATE tasks SET deleted_at = last_update WHERE is_deleted IS true")

    op.drop_column('tasks', 'is_deleted')

    # NOTE: autogenerate also proposed dropping ix_tasks_metadata_gin here — a known false
    # positive (that index isn't declared via SQLAlchemy Column metadata; see d5cef99c534f).
    # Left untouched.


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'tasks', sa.Column('is_deleted', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False)
    )
    op.execute("UPDATE tasks SET is_deleted = (deleted_at IS NOT NULL)")
    op.drop_column('tasks', 'deleted_at')
