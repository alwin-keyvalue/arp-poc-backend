"""add processed_email_id to task_change_history

Revision ID: ba2714bec960
Revises: c8d83da1ad08
Create Date: 2026-07-23 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba2714bec960'
down_revision: Union[str, Sequence[str], None] = 'c8d83da1ad08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('task_change_history', sa.Column('processed_email_id', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_task_change_history_processed_email_id',
        'task_change_history',
        'processed_emails',
        ['processed_email_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_task_change_history_processed_email_id', 'task_change_history', type_='foreignkey')
    op.drop_column('task_change_history', 'processed_email_id')
