"""add processed emails table for dedup

Revision ID: b552b3105e4e
Revises: d5cef99c534f
Create Date: 2026-07-16 15:26:36.069109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b552b3105e4e'
down_revision: Union[str, Sequence[str], None] = 'd5cef99c534f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('processed_emails',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.String(length=255), nullable=False),
    sa.Column('processed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'message_id', name='uq_processed_emails_user_id_message_id')
    )
    # NOTE: autogenerate also proposed dropping ix_tasks_metadata_gin here — a false positive.
    # That index isn't declared via SQLAlchemy Column metadata (it was hand-added with a raw
    # op.create_index using the postgresql_using='gin' opclass in d5cef99c534f), so autogenerate
    # can't see it as "belonging" to the model and treats it as drift. Left untouched.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('processed_emails')
