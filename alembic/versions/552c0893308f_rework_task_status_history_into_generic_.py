"""rework task status history into generic task change history

Revision ID: 552c0893308f
Revises: e7a1c2b3d4f5
Create Date: 2026-07-21 18:13:25.563168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '552c0893308f'
down_revision: Union[str, Sequence[str], None] = 'e7a1c2b3d4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('task_status_history', 'task_change_history')
    op.execute(
        "ALTER TABLE task_change_history RENAME CONSTRAINT fk_task_status_history_task_id "
        "TO fk_task_change_history_task_id"
    )
    op.execute("ALTER INDEX ix_task_status_history_task_id RENAME TO ix_task_change_history_task_id")

    # New column: which Task field this row records a change to. Every existing row predates
    # this rework and was exclusively a status transition, so backfill accordingly.
    op.add_column('task_change_history', sa.Column('field_name', sa.String(length=50), nullable=True))
    op.execute("UPDATE task_change_history SET field_name = 'status'")
    op.alter_column('task_change_history', 'field_name', nullable=False)

    # from_status/to_status -> old_value/new_value, now JSONB since different tracked fields
    # have different shapes (plain strings, lists, ISO dates) instead of always a status string.
    op.alter_column('task_change_history', 'from_status', new_column_name='old_value')
    op.execute(
        "ALTER TABLE task_change_history ALTER COLUMN old_value TYPE JSONB "
        "USING (CASE WHEN old_value IS NULL THEN NULL ELSE to_jsonb(old_value) END)"
    )

    op.alter_column('task_change_history', 'to_status', new_column_name='new_value')
    op.execute("ALTER TABLE task_change_history ALTER COLUMN new_value TYPE JSONB USING to_jsonb(new_value)")
    # to_status was NOT NULL (a status transition always moves to *some* status); new_value
    # must be nullable now since e.g. clearing a description sets the new value to null.
    op.alter_column('task_change_history', 'new_value', nullable=True)

    # NOTE: autogenerate also proposed dropping ix_tasks_metadata_gin here — a known false
    # positive (that index isn't declared via SQLAlchemy Column metadata; see d5cef99c534f).
    # Left untouched.


def downgrade() -> None:
    """Downgrade schema."""
    # Best-effort restore: the old schema can only represent status transitions. Any row
    # recording a change to a different field has no home in the old shape and is dropped.
    op.execute("DELETE FROM task_change_history WHERE field_name != 'status'")

    op.execute(
        "ALTER TABLE task_change_history ALTER COLUMN new_value TYPE VARCHAR(50) USING new_value #>> '{}'"
    )
    op.alter_column('task_change_history', 'new_value', nullable=False)
    op.alter_column('task_change_history', 'new_value', new_column_name='to_status')

    op.execute(
        "ALTER TABLE task_change_history ALTER COLUMN old_value TYPE VARCHAR(50) USING old_value #>> '{}'"
    )
    op.alter_column('task_change_history', 'old_value', new_column_name='from_status')

    op.drop_column('task_change_history', 'field_name')

    op.execute("ALTER INDEX ix_task_change_history_task_id RENAME TO ix_task_status_history_task_id")
    op.execute(
        "ALTER TABLE task_change_history RENAME CONSTRAINT fk_task_change_history_task_id "
        "TO fk_task_status_history_task_id"
    )
    op.rename_table('task_change_history', 'task_status_history')
