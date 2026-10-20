"""Keep the raw turn text separate from a pending plan revision.

Revision ID: 9e7a2c1d4b60
Revises: 81c6d45f29aa
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e7a2c1d4b60"
down_revision: str | None = "81c6d45f29aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.add_column("agent_runs", sa.Column("parent_plan_id", sa.Uuid()))
    op.add_column(
        "agent_runs",
        sa.Column("task_context", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_foreign_key(
        "fk_agent_runs_parent_plan_id",
        "agent_runs",
        "agent_runs",
        ["parent_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_agent_runs_parent_plan_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "task_context")
    op.drop_column("agent_runs", "parent_plan_id")
