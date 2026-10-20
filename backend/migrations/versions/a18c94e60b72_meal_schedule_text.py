"""餐食安排自由文本，保留已有结构化字段。"""

import sqlalchemy as sa
from alembic import op

revision = "a18c94e60b72"
down_revision = "9e45c732ab10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("meal_plans", sa.Column("schedule_text", sa.Text(), nullable=True))
    for name, kind in [
        ("meal_date", sa.Date()),
        ("meal_type", sa.String(20)),
        ("diners", sa.Integer()),
    ]:
        op.alter_column("meal_plans", name, existing_type=kind, nullable=True)


def downgrade():
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT 1 FROM meal_plans WHERE meal_date IS NULL OR meal_type IS NULL OR diners IS NULL LIMIT 1"
        )
    ).first():
        raise RuntimeError("存在自由文本餐食，无法恢复必填结构化字段；请先处理这些记录")
    for name, kind in [
        ("meal_date", sa.Date()),
        ("meal_type", sa.String(20)),
        ("diners", sa.Integer()),
    ]:
        op.alter_column("meal_plans", name, existing_type=kind, nullable=False)
    op.drop_column("meal_plans", "schedule_text")
