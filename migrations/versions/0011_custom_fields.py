"""Add tenant custom field definitions.

Revision ID: 0011_custom_fields
Revises: 0010_invitations
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_custom_fields"
down_revision = "0010_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("options", postgresql.JSONB()),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("entity_type IN ('contact', 'opportunity')", name=op.f("ck_custom_field_definitions_custom_field_entity_type")),
        sa.CheckConstraint("field_type IN ('text', 'number', 'boolean', 'date', 'select', 'multiselect')", name=op.f("ck_custom_field_definitions_custom_field_type")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_custom_field_definitions_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_field_definitions")),
        sa.UniqueConstraint("tenant_id", "entity_type", "name", name=op.f("uq_custom_field_definitions_tenant_id")),
    )
    op.create_index("ix_custom_field_definitions_tenant_id", "custom_field_definitions", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("custom_field_definitions")
