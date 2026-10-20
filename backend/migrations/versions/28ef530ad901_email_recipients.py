"""邮件收件人及通知总开关。"""

import sqlalchemy as sa
from alembic import op

revision = "28ef530ad901"
down_revision = "17da462bc890"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_preferences",
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "email_preferences",
        sa.Column("recipient_emails", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("email_preferences", "recipient_emails")
    op.drop_column("email_preferences", "notifications_enabled")
