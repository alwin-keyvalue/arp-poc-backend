"""replace task assignee name with assignee_id fk to users

Revision ID: 46191d549b50
Revises: a1b2c3d4e5f6
Create Date: 2026-07-13 17:40:52.139460

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46191d549b50'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_tasks_assignee_id_users"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('assignee_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(FK_NAME, 'tasks', 'users', ['assignee_id'], ['id'])
    op.drop_column('tasks', 'assignee')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('tasks', sa.Column('assignee', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.drop_constraint(FK_NAME, 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'assignee_id')
