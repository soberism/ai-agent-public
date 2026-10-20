"""Close notifications for retired collaborator invitations."""

from alembic import op

revision = "a93c24d05ef1"
down_revision = "f82b13c94de0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE kind = 'invitation' AND invitation_id IN (SELECT id FROM household_participants WHERE role = 'helper') AND read_at IS NULL"
    )


def downgrade():
    # Previously closed invitations must not become actionable again.
    pass
