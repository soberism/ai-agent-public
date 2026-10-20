"""Persist answer-linked follow-up options.

Revision ID: 4a6b8c2d9e10
Revises: 9e7a2c1d4b60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a6b8c2d9e10"
down_revision: str | None = "9e7a2c1d4b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.add_column(
        "agent_runs",
        sa.Column("suggestions", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("assistant_messages", sa.Column("suggestions", sa.JSON()))


def downgrade():
    op.drop_column("assistant_messages", "suggestions")
    op.drop_column("agent_runs", "suggestions")
