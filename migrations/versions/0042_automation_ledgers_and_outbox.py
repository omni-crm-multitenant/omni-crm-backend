"""Add automation action ledger and transactional event outbox.

Revision ID: 0042_automation_ledgers_and_outbox
Revises: 0041_ai_usage_ledgers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0042_automation_ledgers_and_outbox"
down_revision = "0041_ai_usage_ledgers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_action_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("send_intent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown', 'cancelled')", name="automation_action_attempt_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["automation_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "execution_id", "action_index", name="uq_automation_action_execution_index"),
    )
    op.create_index("ix_automation_action_attempts_tenant_id", "automation_action_attempts", ["tenant_id"])
    op.create_index("ix_automation_action_attempts_pending", "automation_action_attempts", ["tenant_id", "status", "next_attempt_at"])
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_tenant_id", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_automation_action_attempts_pending", table_name="automation_action_attempts")
    op.drop_index("ix_automation_action_attempts_tenant_id", table_name="automation_action_attempts")
    op.drop_table("automation_action_attempts")
