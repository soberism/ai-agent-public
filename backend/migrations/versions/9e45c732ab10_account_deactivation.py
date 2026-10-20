"""停用登录凭证，保留业务数据及邮箱恢复关联。"""

import sqlalchemy as sa
from alembic import op

revision = "9e45c732ab10"
down_revision = "7d903c125e64"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    # 停用账号不能在回滚后恢复登录。
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM users WHERE auth_version > 0")):
        raise RuntimeError("存在账号注销历史，不能移除账号状态；请先完成恢复或专门迁移")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "active")
