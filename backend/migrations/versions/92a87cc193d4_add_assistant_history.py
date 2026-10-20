"""add assistant history

Revision ID: 92a87cc193d4
Revises: 5cdd828c36fe
"""

import sqlalchemy as sa
from alembic import op

revision = "92a87cc193d4"
down_revision = "5cdd828c36fe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_thread_owner_updated",
        "assistant_threads",
        ["owner_id", "updated_at"],
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=9), nullable=False),
        sa.Column("content", sa.String(length=1000), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=True),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("action_label", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user','assistant')", name="ck_assistant_message_role"
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["assistant_threads.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_message_thread_created",
        "assistant_messages",
        ["thread_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_message_thread_created", table_name="assistant_messages"
    )
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_thread_owner_updated", table_name="assistant_threads")
    op.drop_table("assistant_threads")
