"""Add recoverable automation executions.

Revision ID: 0034_automation_executions
Revises: 0033_automation_rules
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0034_automation_executions"
down_revision = "0033_automation_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), server_default="received", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("result", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('received', 'processing', 'success', 'partial', 'failed', 'dead_letter', 'skipped_depth_limit')", name=op.f("ck_automation_executions_automation_execution_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_automation_executions_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_executions")),
        sa.UniqueConstraint("tenant_id", "rule_id", "event_id", name=op.f("uq_automation_executions_event")),
    )
    op.create_index("ix_automation_executions_tenant_id", "automation_executions", ["tenant_id"])
    op.create_index("ix_automation_executions_pending", "automation_executions", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("automation_executions")
