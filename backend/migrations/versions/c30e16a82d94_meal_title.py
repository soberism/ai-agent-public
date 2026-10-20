"""餐食独立可选标题，历史记录按菜品生成。"""

import sqlalchemy as sa
from alembic import op

revision = "c30e16a82d94"
down_revision = "b29d05f71c83"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("meal_plans", sa.Column("title", sa.String(15), nullable=True))
    op.execute("UPDATE meal_plans SET title = LEFT(dish, 15)")


def downgrade():
    op.drop_column("meal_plans", "title")
