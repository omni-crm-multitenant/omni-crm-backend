"""Add tenant contacts and dedup indexes.

Revision ID: 0012_contacts
Revises: 0011_custom_fields
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_contacts"
down_revision = "0011_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_channel_assets_tenant_identity"),
        "channel_assets",
        ["tenant_id", "id", "channel"],
    )
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(255)),
        sa.Column("source_channel", sa.String(30)),
        sa.Column("source_campaign_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("custom_fields", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived', 'deleted')", name=op.f("ck_contacts_contact_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_contacts_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_contacts_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_contacts_tenant_identity")),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
    op.create_index("ix_contacts_owner_user_id", "contacts", ["owner_user_id"])
    op.create_index("ix_contacts_tenant_phone", "contacts", ["tenant_id", "phone"])
    op.create_index("ix_contacts_tenant_email", "contacts", ["tenant_id", "email"])


def downgrade() -> None:
    op.drop_table("contacts")
    op.drop_constraint(op.f("uq_channel_assets_tenant_identity"), "channel_assets", type_="unique")
