"""add labels and task_labels tables

Revision ID: 5e28c0b33ef3
Revises: 812ebfaabc17
Create Date: 2026-07-22 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e28c0b33ef3'
down_revision: Union[str, Sequence[str], None] = '812ebfaabc17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'labels',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_labels'),
        sa.UniqueConstraint('name', name='uq_labels_name'),
    )

    op.create_table(
        'task_labels',
        sa.Column('task_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('label_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('labeled_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_labels_task_id'),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], name='fk_task_labels_label_id'),
        sa.PrimaryKeyConstraint('task_id', 'label_id', name='pk_task_labels'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('task_labels')
    op.drop_table('labels')
