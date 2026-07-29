"""seed system user

Revision ID: 9cde95906ab3
Revises: 647adb7bb49a
Create Date: 2026-07-27 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9cde95906ab3'
down_revision: Union[str, Sequence[str], None] = '647adb7bb49a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000000'
SYSTEM_USER_EMAIL = 'admin@arp.com'

users_table = sa.table(
    'users',
    sa.column('id', sa.Uuid(as_uuid=True)),
    sa.column('email', sa.String),
    sa.column('display_name', sa.String),
    sa.column('role', sa.String),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        users_table.insert().values(
            id=SYSTEM_USER_ID,
            email=SYSTEM_USER_EMAIL,
            display_name='System',
            role='admin',
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(users_table.delete().where(users_table.c.id == SYSTEM_USER_ID))
