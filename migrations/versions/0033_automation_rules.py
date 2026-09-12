"""Add validated automation rules.

Revision ID: 0033_automation_rules
Revises: 0032_assignment_rotation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0033_automation_rules"
down_revision = "0032_assignment_rotation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.String(40), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("clock", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("trigger_type IN ('lead_created', 'message_received', 'stage_changed', 'customer_unanswered', 'team_unanswered', 'task_created', 'opportunity_won', 'opportunity_lost')", name=op.f("ck_automation_rules_automation_rule_trigger_type")),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name=op.f("ck_automation_rules_automation_rule_duration")),
        sa.CheckConstraint("clock IS NULL OR clock IN ('elapsed', 'business')", name=op.f("ck_automation_rules_automation_rule_clock")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_automation_rules_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_rules")),
    )
    op.create_index("ix_automation_rules_tenant_id", "automation_rules", ["tenant_id"])
    op.create_index("ix_automation_rules_tenant_enabled", "automation_rules", ["tenant_id", "enabled"])


def downgrade() -> None:
    op.drop_table("automation_rules")
