"""每餐独立保存偏好与限制，保留历史全局记录。"""

import sqlalchemy as sa
from alembic import op

revision = "7d903c125e64"
down_revision = "6c8f2b014d53"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "meal_plans",
        sa.Column(
            "preferences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade():
    op.drop_column("meal_plans", "preferences")
