"""add teams identity fields to users

Revision ID: 5297b78618ba
Revises: a1b2c3d4e5f6
Create Date: 2026-07-13 16:45:01.086000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5297b78618ba'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # IF NOT EXISTS guards make this safe to re-run if a prior deploy attempt
    # partially applied it before failing.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS aad_object_id VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS teams_conversation_reference JSON")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_aad_object_id ON users (aad_object_id)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_users_aad_object_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS teams_conversation_reference")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS aad_object_id")
