"""change task_notes.created_by to a user fk

Revision ID: c8d83da1ad08
Revises: 9860b960c616
Create Date: 2026-07-22 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d83da1ad08'
down_revision: Union[str, Sequence[str], None] = '9860b960c616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # created_by used to hold a free-text display label (name/oid/email) — no reliable mapping
    # from that string to a users.id, so the column is dropped and recreated as a proper FK
    # rather than migrated in place.
    op.drop_column('task_notes', 'created_by')
    op.add_column('task_notes', sa.Column('created_by', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_task_notes_created_by', 'task_notes', 'users', ['created_by'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_task_notes_created_by', 'task_notes', type_='foreignkey')
    op.drop_column('task_notes', 'created_by')
    op.add_column('task_notes', sa.Column('created_by', sa.String(length=255), nullable=True))
