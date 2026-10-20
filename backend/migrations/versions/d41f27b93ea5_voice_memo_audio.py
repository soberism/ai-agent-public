"""为语音备忘保留原始音频，兼容历史文字备忘。"""

import sqlalchemy as sa
from alembic import op

revision = "d41f27b93ea5"
down_revision = "c30e16a82d94"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("voice_memos", sa.Column("audio", sa.LargeBinary(), nullable=True))
    op.add_column("voice_memos", sa.Column("mime_type", sa.String(30), nullable=True))


def downgrade():
    op.drop_column("voice_memos", "mime_type")
    op.drop_column("voice_memos", "audio")
