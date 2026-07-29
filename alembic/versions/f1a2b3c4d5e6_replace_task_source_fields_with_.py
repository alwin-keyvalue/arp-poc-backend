"""replace task source_email_id/source_user with source_processed_email_id

Revision ID: f1a2b3c4d5e6
Revises: c79d3b295fd4
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'c79d3b295fd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('tasks', 'source_email_id')
    op.drop_column('tasks', 'source_user')
    op.add_column('tasks', sa.Column('source_processed_email_id', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_tasks_source_processed_email_id',
        'tasks',
        'processed_emails',
        ['source_processed_email_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_tasks_source_processed_email_id', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'source_processed_email_id')
    op.add_column('tasks', sa.Column('source_user', sa.String(length=255), nullable=True))
    op.add_column('tasks', sa.Column('source_email_id', sa.String(length=255), nullable=True))
