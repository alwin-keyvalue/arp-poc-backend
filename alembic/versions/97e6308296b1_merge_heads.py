"""merge heads

Revision ID: 97e6308296b1
Revises: 46191d549b50, 5297b78618ba
Create Date: 2026-07-13 18:40:50.922934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97e6308296b1'
down_revision: Union[str, Sequence[str], None] = ('46191d549b50', '5297b78618ba')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
