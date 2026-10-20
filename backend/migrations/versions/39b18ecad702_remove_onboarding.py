"""移除暂不实现的新手引导状态。"""

import sqlalchemy as sa
from alembic import op

revision = "39b18ecad702"
down_revision = "28ef530ad901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
