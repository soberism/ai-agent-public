"""为已有餐食补齐关联购物清单，保留已有清单和商品。"""

from alembic import op

revision = "6c8f2b014d53"
down_revision = "5b7e1a903c42"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO shopping_lists (id, owner_id, meal_id, title, items, status, created_at)
        SELECT gen_random_uuid(), m.owner_id, m.id,
               LEFT(m.meal_date::text || ' · ' || m.dish, 100),
               '[]'::json, 'draft', NOW()
        FROM meal_plans m
        WHERE NOT EXISTS (SELECT 1 FROM shopping_lists s WHERE s.meal_id = m.id)
    """)


def downgrade():
    # 数据补齐回退时保留清单，避免删除用户随后添加的商品。
    pass
