"""Add shared API idempotency reservations.

Revision ID: 0043_api_idempotency
Revises: 0042_automation_ledgers_and_outbox
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0043_api_idempotency"
down_revision = "0042_automation_ledgers_and_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_payload", postgresql.JSONB()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "endpoint", "key", name="uq_api_idempotency_scope"),
    )
    op.create_index("ix_api_idempotency_keys_tenant_id", "api_idempotency_keys", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_api_idempotency_keys_tenant_id", table_name="api_idempotency_keys")
    op.drop_table("api_idempotency_keys")
