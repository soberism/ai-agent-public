"""邮件发送记录增加账号级幂等键。"""

import sqlalchemy as sa
from alembic import op

revision = "06c9e14ab732"
down_revision = "4a6d0f8b2e31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_deliveries", sa.Column("dedupe_key", sa.String(80), nullable=True)
    )
    op.create_unique_constraint(
        "uq_email_delivery_dedupe", "email_deliveries", ["owner_id", "dedupe_key"]
    )


def downgrade():
    op.drop_constraint("uq_email_delivery_dedupe", "email_deliveries", type_="unique")
    op.drop_column("email_deliveries", "dedupe_key")
