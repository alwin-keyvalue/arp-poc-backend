"""multiple task assignees, remove watchers

Revision ID: 07aed69a36fc
Revises: 98bd7840e654
Create Date: 2026-07-15 15:22:30.460699

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '07aed69a36fc'
down_revision: Union[str, Sequence[str], None] = '98bd7840e654'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('task_assignees',
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('task_id', 'user_id')
    )
    # Preserve existing single-assignee data before dropping the column.
    op.execute(
        "INSERT INTO task_assignees (task_id, user_id, assigned_at) "
        "SELECT id, assignee_id, now() FROM tasks WHERE assignee_id IS NOT NULL"
    )
    op.drop_constraint(op.f('fk_tasks_assignee_id_users'), 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'assignee_id')
    op.drop_column('tasks', 'watchers')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'tasks',
        sa.Column(
            'watchers', postgresql.JSON(astext_type=sa.Text()), autoincrement=False,
            nullable=False, server_default='[]',
        ),
    )
    op.add_column('tasks', sa.Column('assignee_id', sa.UUID(), autoincrement=False, nullable=True))
    # Best-effort restore: a task can have multiple assignees post-upgrade, but assignee_id only
    # holds one, so pick the earliest-assigned user per task. Any others are dropped.
    op.execute(
        "UPDATE tasks SET assignee_id = sub.user_id FROM ("
        "  SELECT DISTINCT ON (task_id) task_id, user_id FROM task_assignees "
        "  ORDER BY task_id, assigned_at ASC"
        ") AS sub WHERE tasks.id = sub.task_id"
    )
    op.create_foreign_key(op.f('fk_tasks_assignee_id_users'), 'tasks', 'users', ['assignee_id'], ['id'])
    op.drop_table('task_assignees')
