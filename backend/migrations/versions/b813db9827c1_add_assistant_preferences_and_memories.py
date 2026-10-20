"""add assistant preferences and memories

Revision ID: b813db9827c1
Revises: b73f4d28a610
Create Date: 2026-09-16 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b813db9827c1"
down_revision: str | None = "b73f4d28a610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_profiles",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("custom_instructions", sa.String(length=2000), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.create_table(
        "assistant_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(content) BETWEEN 1 AND 500", name="ck_memory_content"
        ),
        sa.CheckConstraint("source IN ('user','assistant')", name="ck_memory_source"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_owner_updated",
        "assistant_memories",
        ["owner_id", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_owner_updated", table_name="assistant_memories")
    op.drop_table("assistant_memories")
    op.drop_table("assistant_profiles")
