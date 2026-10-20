"""Retire collaborator access without promoting accounts or deleting items."""

from alembic import op

revision = "f82b13c94de0"
down_revision = "e719d02f83ac"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE household_participants SET status = CASE WHEN status = 'pending' THEN 'rejected' ELSE 'removed' END WHERE role = 'helper' AND status IN ('pending', 'active')"
    )
    op.execute(
        "DELETE FROM item_sharing_members WHERE (kind, resource_id) IN (SELECT kind, resource_id FROM item_sharing WHERE scope = 'helpers')"
    )
    op.execute(
        "UPDATE item_sharing SET scope = 'private', household_id = NULL WHERE scope = 'helpers'"
    )
    op.drop_constraint("ck_item_sharing_scope", "item_sharing", type_="check")
    op.create_check_constraint(
        "ck_item_sharing_scope",
        "item_sharing",
        "scope IN ('private','household','members')",
    )


def downgrade():
    # Restoring schema does not automatically restore revoked access.
    op.drop_constraint("ck_item_sharing_scope", "item_sharing", type_="check")
    op.create_check_constraint(
        "ck_item_sharing_scope",
        "item_sharing",
        "scope IN ('private','household','members','helpers')",
    )
