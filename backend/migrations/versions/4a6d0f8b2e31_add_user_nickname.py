"""add user nickname

Revision ID: 4a6d0f8b2e31
Revises: f824c0e153b2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a6d0f8b2e31"
down_revision: str | None = "f824c0e153b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.add_column("users", sa.Column("nickname", sa.String(30)))


def downgrade():
    op.drop_column("users", "nickname")
