"""Add first-response KPI event storage.

Revision ID: 0046_kpi_events
Revises: 0045_outbox_polling
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0046_kpi_events"
down_revision = "0045_outbox_polling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("response_window_id", postgresql.UUID(as_uuid=True)))
    op.add_column("conversations", sa.Column("response_window_started_at", sa.DateTime(timezone=True)))
    op.create_index("ix_conversations_response_window_id", "conversations", ["response_window_id"])
    op.create_table(
        "kpi_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_window_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True)),
        sa.Column("responder_type", sa.String(20), nullable=False),
        sa.Column("responder_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ai_model", sa.String(120)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("resolved_by_ai", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("responder_type IN ('agent', 'ai', 'automation')", name="kpi_responder_type"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name="fk_kpi_events_tenant_conversation"),
        sa.ForeignKeyConstraint(["responder_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "response_window_id", name="uq_kpi_events_response_window"),
    )
    op.create_index("ix_kpi_events_tenant_id", "kpi_events", ["tenant_id"])
    op.create_index("ix_kpi_events_tenant_received", "kpi_events", ["tenant_id", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_kpi_events_tenant_received", table_name="kpi_events")
    op.drop_index("ix_kpi_events_tenant_id", table_name="kpi_events")
    op.drop_table("kpi_events")
    op.drop_index("ix_conversations_response_window_id", table_name="conversations")
    op.drop_column("conversations", "response_window_started_at")
    op.drop_column("conversations", "response_window_id")
