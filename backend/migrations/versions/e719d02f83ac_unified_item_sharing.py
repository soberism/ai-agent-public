"""Unified item visibility; existing items remain private."""

import sqlalchemy as sa
from alembic import op

revision = "e719d02f83ac"
down_revision = "d41f27b93ea5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "item_sharing",
        sa.Column("kind", sa.String(30), primary_key=True),
        sa.Column("resource_id", sa.Uuid(), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
        ),
        sa.CheckConstraint(
            "scope IN ('private','household','members','helpers')",
            name="ck_item_sharing_scope",
        ),
    )
    op.create_table(
        "item_sharing_members",
        sa.Column("kind", sa.String(30), primary_key=True),
        sa.Column("resource_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.ForeignKeyConstraint(
            ["kind", "resource_id"],
            ["item_sharing.kind", "item_sharing.resource_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("item_sharing_members")
    op.drop_table("item_sharing")
