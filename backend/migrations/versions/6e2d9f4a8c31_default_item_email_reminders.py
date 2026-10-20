"""Enable item email reminders by default for all accounts."""

from alembic import op

revision = "6e2d9f4a8c31"
down_revision = "3f7c61e8a904"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE email_preferences SET reminder_enabled = true, "
        "updated_at = now() WHERE reminder_enabled = false"
    )
    op.alter_column("email_preferences", "reminder_enabled", server_default="true")


def downgrade():
    op.alter_column("email_preferences", "reminder_enabled", server_default="false")
