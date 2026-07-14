"""merge heads

Revision ID: 98bd7840e654
Revises: ac396c71d18f, b2c3d4e5f6a7
Create Date: 2026-07-14 15:00:08.941720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98bd7840e654'
down_revision: Union[str, Sequence[str], None] = ('ac396c71d18f', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
