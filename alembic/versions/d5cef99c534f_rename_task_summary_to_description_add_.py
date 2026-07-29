"""rename task summary to description, add summary and metadata jsonb

Revision ID: d5cef99c534f
Revises: 07aed69a36fc
Create Date: 2026-07-16 12:48:57.322347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5cef99c534f'
down_revision: Union[str, Sequence[str], None] = '07aed69a36fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('description', sa.Text(), nullable=True))
    op.add_column(
        'tasks', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False)
    )

    # The old "summary" column held what's now called "description"; move its data over,
    # then clear "summary" so the newly-added field starts empty as intended.
    op.execute("UPDATE tasks SET description = summary")
    op.execute("UPDATE tasks SET summary = NULL")

    # Preserve the existing single conversation_id as the first entry of the new
    # metadata->conversation_ids array before dropping the column.
    op.execute(
        "UPDATE tasks SET metadata = jsonb_set(metadata, '{conversation_ids}', "
        "jsonb_build_array(conversation_id)) WHERE conversation_id IS NOT NULL"
    )
    op.drop_column('tasks', 'conversation_id')

    # GIN (default opclass, not jsonb_path_ops) supports both containment (@>) queries used by
    # get_by_conversation_id and key-existence (?, ?|, ?&) queries if needed later.
    op.create_index('ix_tasks_metadata_gin', 'tasks', ['metadata'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tasks_metadata_gin', table_name='tasks')

    op.add_column('tasks', sa.Column('conversation_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    # Best-effort restore: a task can have multiple conversation_ids post-upgrade, but the old
    # column only holds one. Pick the lexicographically-lowest for determinism; any others (and
    # all of internet_message_ids, which has no home in the old schema) are dropped.
    op.execute(
        "UPDATE tasks SET conversation_id = ("
        "  SELECT MIN(value) FROM jsonb_array_elements_text(metadata -> 'conversation_ids') AS value"
        ")"
    )
    op.drop_column('tasks', 'metadata')

    # Best-effort restore: the old schema only has one "summary" field, so give it back the
    # "description" content (the new post-upgrade "summary" field's data has no home in the old
    # schema and is dropped).
    op.execute("UPDATE tasks SET summary = description")
    op.drop_column('tasks', 'description')
