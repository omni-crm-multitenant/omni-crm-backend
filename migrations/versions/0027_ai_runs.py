"""Add pinned AI execution records.

Revision ID: 0027_ai_runs
Revises: 0026_ai_profiles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_ai_runs"
down_revision = "0026_ai_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_conversations_tenant_identity", "conversations", ["tenant_id", "id"])
    op.create_unique_constraint("uq_ai_profiles_tenant_identity", "ai_profiles", ["tenant_id", "id"])
    op.create_table(
        "ai_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("trigger_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("latency_ms", sa.BigInteger()),
        sa.Column("token_usage", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("control_version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'running', 'success', 'error', 'transferred', 'cancelled')", name=op.f("ck_ai_runs_ai_run_status")),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name=op.f("fk_ai_runs_tenant_conversation")),
        sa.ForeignKeyConstraint(["tenant_id", "profile_id"], ["ai_profiles.tenant_id", "ai_profiles.id"], ondelete="RESTRICT", name=op.f("fk_ai_runs_tenant_profile")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs")),
        sa.UniqueConstraint("tenant_id", "conversation_id", "trigger_message_id", name=op.f("uq_ai_runs_trigger")),
    )
    op.create_index("ix_ai_runs_tenant_id", "ai_runs", ["tenant_id"])
    op.create_index("ix_ai_runs_tenant_conversation", "ai_runs", ["tenant_id", "conversation_id"])


def downgrade() -> None:
    op.drop_table("ai_runs")
    op.drop_constraint("uq_ai_profiles_tenant_identity", "ai_profiles", type_="unique")
    op.drop_constraint("uq_conversations_tenant_identity", "conversations", type_="unique")
