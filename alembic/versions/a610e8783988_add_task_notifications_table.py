"""add task_notifications table

Revision ID: a610e8783988
Revises: ba2714bec960
Create Date: 2026-07-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a610e8783988'
down_revision: Union[str, Sequence[str], None] = 'ba2714bec960'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'task_notifications',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('task_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('origin_type', sa.String(length=20), nullable=False),
        sa.Column('origin_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_notifications_task_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_task_notifications_user_id'),
        sa.PrimaryKeyConstraint('id', name='pk_task_notifications'),
    )
    op.create_index('ix_task_notifications_task_id', 'task_notifications', ['task_id'])
    op.create_index('ix_task_notifications_user_id', 'task_notifications', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_task_notifications_user_id', table_name='task_notifications')
    op.drop_index('ix_task_notifications_task_id', table_name='task_notifications')
    op.drop_table('task_notifications')
