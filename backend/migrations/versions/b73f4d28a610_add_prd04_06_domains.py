"""add family, documents and life planning domains

Revision ID: b73f4d28a610
Revises: a24e3f76c105
"""

import sqlalchemy as sa
from alembic import op

revision = "b73f4d28a610"
down_revision = "a24e3f76c105"
branch_labels = None
depends_on = None


def timestamps():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        timestamps(),
    )
    op.create_index("ix_household_owner", "households", ["owner_id", "created_at"])
    op.create_table(
        "household_participants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        timestamps(),
        sa.UniqueConstraint("household_id", "email", name="uq_household_email"),
    )
    op.create_index(
        "ix_participant_account_status",
        "household_participants",
        ["account_id", "status"],
    )
    op.create_table(
        "household_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("relationship", sa.String(50), nullable=False),
        sa.Column("birth_date", sa.Date()),
        timestamps(),
    )
    op.create_index(
        "ix_profile_household", "household_profiles", ["household_id", "created_at"]
    )
    op.create_table(
        "pets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("species", sa.String(50), nullable=False),
        sa.Column("breed", sa.String(100)),
        timestamps(),
    )
    op.create_index("ix_pet_household", "pets", ["household_id", "created_at"])
    op.create_table(
        "contact_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        timestamps(),
        sa.UniqueConstraint("owner_id", "name", name="uq_contact_group_owner_name"),
    )
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("relationship", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(30)),
        sa.Column("email", sa.String(254)),
        timestamps(),
    )
    op.create_index("ix_contact_owner_name", "contacts", ["owner_id", "name", "id"])
    op.create_table(
        "contact_group_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("contact_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("group_id", "contact_id", name="uq_group_contact"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recipient_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "invitation_id",
            sa.Uuid(),
            sa.ForeignKey("household_participants.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        timestamps(),
    )
    op.create_index(
        "ix_notification_recipient", "notifications", ["recipient_id", "created_at"]
    )

    op.create_table(
        "document_folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        timestamps(),
        sa.UniqueConstraint("owner_id", "name", name="uq_document_folder_owner_name"),
    )
    op.create_table(
        "document_materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "folder_id",
            sa.Uuid(),
            sa.ForeignKey("document_folders.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(300)),
        timestamps(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "content_hash", name="uq_material_owner_hash"),
    )
    op.create_index(
        "ix_material_owner_created",
        "document_materials",
        ["owner_id", "created_at", "id"],
    )
    op.create_table(
        "document_review_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("document_materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("evidence", sa.String(500), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("proposed_date", sa.String(10)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid()),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        timestamps(),
    )
    op.create_index(
        "ix_review_owner_status", "document_review_items", ["owner_id", "status", "id"]
    )

    op.create_table(
        "life_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        timestamps(),
        sa.UniqueConstraint("owner_id", "label", "kind", name="uq_life_preference"),
    )
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("expires_on", sa.Date()),
        timestamps(),
    )
    op.create_index("ix_pantry_owner_name", "pantry_items", ["owner_id", "name", "id"])
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("dish", sa.String(100), nullable=False),
        sa.Column("diners", sa.Integer(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("calendar_events.id", ondelete="SET NULL"),
        ),
        timestamps(),
    )
    op.create_index("ix_meal_owner_date", "meal_plans", ["owner_id", "meal_date", "id"])
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "checklist_id",
            sa.Uuid(),
            sa.ForeignKey("checklists.id", ondelete="SET NULL"),
        ),
        timestamps(),
    )
    op.create_index(
        "ix_shopping_owner_created", "shopping_lists", ["owner_id", "created_at"]
    )
    op.create_table(
        "medical_appointments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("patient_name", sa.String(100), nullable=False),
        sa.Column("provider_name", sa.String(150), nullable=False),
        sa.Column("service_type", sa.String(100), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("scheduled_time", sa.Time(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("calendar_events.id", ondelete="SET NULL"),
        ),
        sa.Column("todo_id", sa.Uuid(), sa.ForeignKey("todos.id", ondelete="SET NULL")),
        timestamps(),
    )
    op.create_index(
        "ix_appointment_owner_date",
        "medical_appointments",
        ["owner_id", "scheduled_date", "id"],
    )


def downgrade() -> None:
    for table in (
        "medical_appointments",
        "shopping_lists",
        "meal_plans",
        "pantry_items",
        "life_preferences",
        "document_review_items",
        "document_materials",
        "document_folders",
        "notifications",
        "contact_group_memberships",
        "contacts",
        "contact_groups",
        "pets",
        "household_profiles",
        "household_participants",
        "households",
    ):
        op.drop_table(table)
