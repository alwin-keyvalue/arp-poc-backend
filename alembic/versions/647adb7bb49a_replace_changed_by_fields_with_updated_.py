"""replace changed_by_oid/name with updated_by fk on task_change_history

Revision ID: 647adb7bb49a
Revises: 65df09499f5c
Create Date: 2026-07-27 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '647adb7bb49a'
down_revision: Union[str, Sequence[str], None] = '65df09499f5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('task_change_history', 'changed_by_oid')
    op.drop_column('task_change_history', 'changed_by_name')
    op.add_column('task_change_history', sa.Column('updated_by', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_task_change_history_updated_by',
        'task_change_history',
        'users',
        ['updated_by'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_task_change_history_updated_by', 'task_change_history', type_='foreignkey')
    op.drop_column('task_change_history', 'updated_by')
    op.add_column('task_change_history', sa.Column('changed_by_name', sa.String(length=255), nullable=True))
    op.add_column('task_change_history', sa.Column('changed_by_oid', sa.String(length=255), nullable=True))
