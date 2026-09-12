"""Add tenant pipelines and ordered stages.

Revision ID: 0024_pipelines
Revises: 0023_ad_sets_ads
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024_pipelines"
down_revision = "0023_ad_sets_ads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_pipelines_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipelines")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_pipelines_tenant_identity")),
    )
    op.create_index("ix_pipelines_tenant_id", "pipelines", ["tenant_id"])
    op.create_index("ix_pipelines_tenant_default", "pipelines", ["tenant_id", "is_default"])
    op.create_table(
        "pipeline_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("terminal_type", sa.String(10), server_default="none", nullable=False),
        sa.CheckConstraint("terminal_type IN ('none', 'won', 'lost')", name=op.f("ck_pipeline_stages_pipeline_stage_terminal_type")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "pipeline_id"], ["pipelines.tenant_id", "pipelines.id"], ondelete="CASCADE", name=op.f("fk_pipeline_stages_tenant_pipeline")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_stages")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_pipeline_stages_tenant_identity")),
        sa.UniqueConstraint("tenant_id", "pipeline_id", "position", name=op.f("uq_pipeline_stages_tenant_pipeline_position")),
    )
    op.create_index("ix_pipeline_stages_tenant_id", "pipeline_stages", ["tenant_id"])
    op.create_index("ix_pipeline_stages_tenant_pipeline", "pipeline_stages", ["tenant_id", "pipeline_id"])


def downgrade() -> None:
    op.drop_table("pipeline_stages")
    op.drop_table("pipelines")
