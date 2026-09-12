"""Add immutable tenant audit and restricted ingress diagnostics.

Revision ID: 0014_audit
Revises: 0013_conversations_messages
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_audit"
down_revision = "0013_conversations_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sanitized_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("actor_type IN ('user', 'ai', 'system', 'integration')", name=op.f("ck_audit_events_audit_actor_type")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name=op.f("fk_audit_events_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_audit_events_actor_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_tenant_time", "audit_events", ["tenant_id", "occurred_at", "id"])
    op.create_table(
        "ingress_diagnostics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("routing_key_hash", sa.String(64)),
        sa.Column("sanitized_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingress_diagnostics")),
    )
    op.execute(
        "CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'AUDIT_EVENTS_ARE_APPEND_ONLY'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation()")
    op.drop_table("ingress_diagnostics")
    op.drop_table("audit_events")
