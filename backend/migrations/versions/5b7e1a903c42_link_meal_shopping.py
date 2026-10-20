"""link meal shopping lists

Revision ID: 5b7e1a903c42
Revises: 39b18ecad702
"""

import sqlalchemy as sa
from alembic import op

revision = "5b7e1a903c42"
down_revision = "39b18ecad702"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shopping_lists", sa.Column("meal_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_shopping_meal",
        "shopping_lists",
        "meal_plans",
        ["meal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_shopping_meal", "shopping_lists", ["meal_id"])


def downgrade():
    op.drop_constraint("uq_shopping_meal", "shopping_lists", type_="unique")
    op.drop_constraint("fk_shopping_meal", "shopping_lists", type_="foreignkey")
    op.drop_column("shopping_lists", "meal_id")
