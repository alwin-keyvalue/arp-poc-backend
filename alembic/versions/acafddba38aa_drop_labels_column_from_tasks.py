"""drop labels column from tasks

Revision ID: acafddba38aa
Revises: 5e28c0b33ef3
Create Date: 2026-07-22 13:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'acafddba38aa'
down_revision: Union[str, Sequence[str], None] = '5e28c0b33ef3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Superseded by the new labels/task_labels relational tables. No data migration into the
    # new tables: any existing string values in this column are dropped, not carried over.
    op.drop_column('tasks', 'labels')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('tasks', sa.Column('labels', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
