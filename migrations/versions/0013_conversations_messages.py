"""Add tenant-safe conversations and messages.

Revision ID: 0013_conversations_messages
Revises: 0012_contacts
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_conversations_messages"
down_revision = "0012_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("ai_mode", sa.String(20), server_default="active", nullable=False),
        sa.Column("control_version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'pending', 'closed')", name=op.f("ck_conversations_conversation_status")),
        sa.CheckConstraint("ai_mode IN ('active', 'handoff_pending', 'human')", name=op.f("ck_conversations_conversation_ai_mode")),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_conversations_tenant_contact")),
        sa.ForeignKeyConstraint(["tenant_id", "channel_asset_id", "channel"], ["channel_assets.tenant_id", "channel_assets.id", "channel_assets.channel"], ondelete="RESTRICT", name=op.f("fk_conversations_tenant_asset_channel")),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_conversations_assigned_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("tenant_id", "id", "channel_asset_id", "channel", name=op.f("uq_conversations_tenant_identity_channel")),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_contact_id", "conversations", ["contact_id"])
    op.create_index("ix_conversations_channel_asset_id", "conversations", ["channel_asset_id"])
    op.create_index("ix_conversations_assigned_user_id", "conversations", ["assigned_user_id"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("author_type", sa.String(20), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("body_text", sa.Text()),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("control_version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("direction IN ('inbound', 'outbound', 'system')", name=op.f("ck_messages_message_direction")),
        sa.CheckConstraint("author_type IN ('contact', 'user', 'ai', 'system')", name=op.f("ck_messages_message_author_type")),
        sa.CheckConstraint("status IN ('queued', 'dispatching', 'sent', 'delivered', 'read', 'failed', 'unknown', 'cancelled')", name=op.f("ck_messages_message_status")),
        sa.CheckConstraint("author_type != 'system' OR provider_message_id IS NULL", name=op.f("ck_messages_system_message_not_dispatched")),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id", "channel_asset_id", "channel"], ["conversations.tenant_id", "conversations.id", "conversations.channel_asset_id", "conversations.channel"], ondelete="CASCADE", name=op.f("fk_messages_conversation_context")),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_messages_author_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_channel_asset_id", "messages", ["channel_asset_id"])
    op.create_index(
        "uq_messages_provider_identity",
        "messages",
        ["tenant_id", "channel_asset_id", "provider_message_id"],
        unique=True,
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_messages_stable_chronology",
        "messages",
        ["tenant_id", "conversation_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
