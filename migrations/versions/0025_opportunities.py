"""Add tenant-scoped opportunities.

Revision ID: 0025_opportunities
Revises: 0024_pipelines
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025_opportunities"
down_revision = "0024_pipelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("loss_reason", sa.String(255)),
        sa.Column("expected_close_at", sa.DateTime(timezone=True)),
        sa.Column("custom_fields", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_opportunities_tenant_contact")),
        sa.ForeignKeyConstraint(["tenant_id", "pipeline_id"], ["pipelines.tenant_id", "pipelines.id"], ondelete="RESTRICT", name=op.f("fk_opportunities_tenant_pipeline")),
        sa.ForeignKeyConstraint(["tenant_id", "stage_id"], ["pipeline_stages.tenant_id", "pipeline_stages.id"], ondelete="RESTRICT", name=op.f("fk_opportunities_tenant_stage")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_opportunities_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_opportunities_tenant_identity")),
    )
    op.create_index("ix_opportunities_tenant_id", "opportunities", ["tenant_id"])
    op.create_index("ix_opportunities_owner_user_id", "opportunities", ["owner_user_id"])
    op.create_index("ix_opportunities_tenant_contact", "opportunities", ["tenant_id", "contact_id"])
    op.create_index("ix_opportunities_tenant_pipeline", "opportunities", ["tenant_id", "pipeline_id"])


def downgrade() -> None:
    op.drop_table("opportunities")
