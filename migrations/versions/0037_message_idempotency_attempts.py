"""Add local message idempotency and provider attempt evidence.

Revision ID: 0037_message_idempotency_attempts
Revises: 0036_pipeline_ai_transition
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_message_idempotency_attempts"
down_revision = "0036_pipeline_ai_transition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Later revision identifiers exceed Alembic's default VARCHAR(32) column.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    op.add_column("messages", sa.Column("client_idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("messages", sa.Column("client_request_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_messages_client_idempotency",
        "messages",
        ["tenant_id", "conversation_id", "client_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("client_idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("client_idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "message_send_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('dispatching', 'accepted', 'rejected', 'unknown')", name="message_send_attempt_status"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_send_attempts_tenant_id", "message_send_attempts", ["tenant_id"])
    op.create_index("ix_message_send_attempts_message", "message_send_attempts", ["tenant_id", "message_id", "attempt_number"])


def downgrade() -> None:
    op.drop_index("ix_message_send_attempts_message", table_name="message_send_attempts")
    op.drop_index("ix_message_send_attempts_tenant_id", table_name="message_send_attempts")
    op.drop_table("message_send_attempts")
    op.drop_index("uq_messages_client_idempotency", table_name="messages")
    op.drop_column("messages", "client_request_hash")
    op.drop_column("messages", "client_idempotency_key")
