"""Keep historical object references separate from user-visible result cards.

Revision ID: 7c2e9a4b6d10
Revises: 4a6b8c2d9e10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c2e9a4b6d10"
down_revision: str | None = "4a6b8c2d9e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.add_column("assistant_messages", sa.Column("context_refs", sa.JSON()))


def downgrade():
    op.drop_column("assistant_messages", "context_refs")
