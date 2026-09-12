"""Add versioned tenant AI profiles.

Revision ID: 0026_ai_profiles
Revises: 0025_opportunities
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_ai_profiles"
down_revision = "0025_opportunities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("service_catalog", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("faq", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("tone", sa.String(80), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_ai_profiles_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_ai_profiles_created_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_profiles")),
        sa.UniqueConstraint("tenant_id", "version", name=op.f("uq_ai_profiles_tenant_version")),
    )
    op.create_index("ix_ai_profiles_tenant_id", "ai_profiles", ["tenant_id"])
    op.create_index("uq_ai_profiles_active_tenant", "ai_profiles", ["tenant_id"], unique=True, postgresql_where=sa.text("active = true"))


def downgrade() -> None:
    op.drop_table("ai_profiles")
