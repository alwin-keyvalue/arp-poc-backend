"""add role to users

Revision ID: 9860b960c616
Revises: a2570c2ea5da
Create Date: 2026-07-22 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9860b960c616'
down_revision: Union[str, Sequence[str], None] = 'a2570c2ea5da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('role', sa.String(length=50), server_default=sa.text("'user'"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
