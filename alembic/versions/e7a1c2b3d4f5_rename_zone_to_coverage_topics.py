"""rename users.zone to coverage_topics as text array

Revision ID: e7a1c2b3d4f5
Revises: b552b3105e4e
Create Date: 2026-07-17 15:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a1c2b3d4f5"
down_revision: Union[str, Sequence[str], None] = "b552b3105e4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _user_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns("users")}


def upgrade() -> None:
    cols = _user_columns()
    if "coverage_topics" in cols:
        return

    if "zone" in cols:
        op.alter_column("users", "zone", new_column_name="coverage_topics")
        op.execute(
            sa.text(
                """
                ALTER TABLE users
                  ALTER COLUMN coverage_topics DROP DEFAULT,
                  ALTER COLUMN coverage_topics TYPE VARCHAR[]
                    USING (
                      CASE
                        WHEN coverage_topics IS NULL OR btrim(coverage_topics) = '' THEN '{}'::VARCHAR[]
                        ELSE ARRAY[coverage_topics]::VARCHAR[]
                      END
                    ),
                  ALTER COLUMN coverage_topics SET DEFAULT '{}',
                  ALTER COLUMN coverage_topics SET NOT NULL
                """
            )
        )
        return

    op.add_column(
        "users",
        sa.Column(
            "coverage_topics",
            sa.ARRAY(sa.String()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    cols = _user_columns()
    if "coverage_topics" not in cols:
        return

    # Prefer restoring zone when that was the original column on this DB.
    op.execute(
        sa.text(
            """
            ALTER TABLE users
              ALTER COLUMN coverage_topics DROP DEFAULT,
              ALTER COLUMN coverage_topics DROP NOT NULL,
              ALTER COLUMN coverage_topics TYPE VARCHAR(64)
                USING (
                  CASE
                    WHEN coverage_topics IS NULL OR cardinality(coverage_topics) = 0 THEN NULL
                    ELSE coverage_topics[1]
                  END
                )
            """
        )
    )
    op.alter_column("users", "coverage_topics", new_column_name="zone")
