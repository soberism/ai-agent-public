"""Replace daily email summary setting with item reminder lead time."""

import sqlalchemy as sa
from alembic import op

revision = "3f7c61e8a904"
down_revision = "a93c24d05ef1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_preferences",
        sa.Column(
            "reminder_minutes", sa.Integer(), nullable=False, server_default="30"
        ),
    )
    op.execute(
        "UPDATE email_preferences SET reminder_enabled = daily_enabled, daily_enabled = false"
    )
    op.alter_column("email_preferences", "reminder_enabled", server_default="false")


def downgrade():
    op.execute(
        "UPDATE email_preferences SET daily_enabled = reminder_enabled, reminder_enabled = false"
    )
    op.drop_column("email_preferences", "reminder_minutes")
