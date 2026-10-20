"""保留完整邮件摘要正文。"""

import sqlalchemy as sa
from alembic import op

revision = "17da462bc890"
down_revision = "06c9e14ab732"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "email_deliveries",
        "body",
        existing_type=sa.String(2000),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "email_deliveries",
        "body",
        existing_type=sa.Text(),
        type_=sa.String(2000),
        existing_nullable=False,
    )
