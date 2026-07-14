"""allow multiple folder subscriptions per user

Revision ID: b2c3d4e5f6a7
Revises: 46191d549b50
Create Date: 2026-07-14 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "97e6308296b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("graph_subscriptions_user_id_key", "graph_subscriptions", type_="unique")
    op.create_unique_constraint(
        "uq_graph_subscriptions_user_id_resource",
        "graph_subscriptions",
        ["user_id", "resource"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_graph_subscriptions_user_id_resource",
        "graph_subscriptions",
        type_="unique",
    )
    op.create_unique_constraint(
        "graph_subscriptions_user_id_key",
        "graph_subscriptions",
        ["user_id"],
    )
