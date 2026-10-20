"""add platform settings

Revision ID: caa30fef726c
Revises: 92a87cc193d4
"""

import sqlalchemy as sa
from alembic import op

revision = "caa30fef726c"
down_revision = "92a87cc193d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET onboarding_completed_at = CURRENT_TIMESTAMP")


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
