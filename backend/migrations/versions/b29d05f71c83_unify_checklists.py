"""购物清单迁入通用清单，旧表保留历史数据和链接映射。"""

import json
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op

revision = "b29d05f71c83"
down_revision = "a18c94e60b72"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shopping_lists", sa.Column("unified_checklist_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_shopping_unified_checklist",
        "shopping_lists",
        "checklists",
        ["unified_checklist_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_shopping_unified_checklist", "shopping_lists", ["unified_checklist_id"]
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text("SELECT id, owner_id, title, items, created_at FROM shopping_lists")
        )
        .mappings()
        .all()
    )
    for row in rows:
        migrate_list(connection, row)


def migrate_list(connection, row):
    checklist_id = uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO checklists (id, owner_id, title, pinned, created_at, updated_at) VALUES (:id, :owner, :title, false, :created, :created)"
        ),
        {
            "id": checklist_id,
            "owner": row["owner_id"],
            "title": row["title"],
            "created": row["created_at"],
        },
    )
    items = json.loads(row["items"]) if isinstance(row["items"], str) else row["items"]
    for position, item in enumerate(items):
        quantity = item.get("quantity", 1)
        unit = item.get("unit", "")
        category = item.get("category", "")
        extra = (
            ""
            if quantity == 1 and not unit and not category
            else f" {quantity}{unit}" + (f" · {category}" if category else "")
        )
        title = item["name"] + extra
        if len(title) > 200:
            raise RuntimeError("购物项转换后超过200字，迁移回滚以保留数据")
        item_id = UUID(item["id"]) if item.get("id") else uuid4()
        if connection.scalar(
            sa.text("SELECT 1 FROM checklist_items WHERE id = :id"), {"id": item_id}
        ):
            item_id = uuid4()
        connection.execute(
            sa.text(
                "INSERT INTO checklist_items (id, checklist_id, title, completed, position, created_at) VALUES (:id, :list, :title, :completed, :position, :created)"
            ),
            {
                "id": item_id,
                "list": checklist_id,
                "title": title,
                "completed": item.get("purchased", False),
                "position": position,
                "created": row["created_at"],
            },
        )
    connection.execute(
        sa.text(
            "UPDATE shopping_lists SET unified_checklist_id = :list WHERE id = :id"
        ),
        {"list": checklist_id, "id": row["id"]},
    )


def downgrade():
    op.drop_constraint(
        "uq_shopping_unified_checklist", "shopping_lists", type_="unique"
    )
    op.drop_constraint(
        "fk_shopping_unified_checklist", "shopping_lists", type_="foreignkey"
    )
    op.drop_column("shopping_lists", "unified_checklist_id")
    # 保留已迁入的清单和后续修改，不删除用户数据。
