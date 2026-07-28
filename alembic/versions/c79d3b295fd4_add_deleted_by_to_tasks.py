"""add deleted_by to tasks

Revision ID: c79d3b295fd4
Revises: 9cde95906ab3
Create Date: 2026-07-28 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c79d3b295fd4'
down_revision: Union[str, Sequence[str], None] = '9cde95906ab3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('deleted_by', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_tasks_deleted_by',
        'tasks',
        'users',
        ['deleted_by'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_tasks_deleted_by', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'deleted_by')
