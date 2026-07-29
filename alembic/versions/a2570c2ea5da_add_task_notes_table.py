"""add task_notes table

Revision ID: a2570c2ea5da
Revises: acafddba38aa
Create Date: 2026-07-22 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2570c2ea5da'
down_revision: Union[str, Sequence[str], None] = 'acafddba38aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'task_notes',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('task_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_notes_task_id'),
        sa.PrimaryKeyConstraint('id', name='pk_task_notes'),
    )
    op.create_index('ix_task_notes_task_id', 'task_notes', ['task_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_task_notes_task_id', table_name='task_notes')
    op.drop_table('task_notes')
