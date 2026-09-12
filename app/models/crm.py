from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


json_type = JSON().with_variant(postgresql.JSONB(), "postgresql")
tags_type = JSON().with_variant(postgresql.ARRAY(Text()), "postgresql")


class CustomFieldDefinition(TimestampMixin, Base):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "name"),
        CheckConstraint("entity_type IN ('contact', 'opportunity')", name="custom_field_entity_type"),
        CheckConstraint(
            "field_type IN ('text', 'number', 'boolean', 'date', 'select', 'multiselect')",
            name="custom_field_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    options: Mapped[list[str] | None] = mapped_column(json_type)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_contacts_tenant_identity"),
        CheckConstraint("status IN ('active', 'archived', 'deleted')", name="contact_status"),
        Index("ix_contacts_tenant_phone", "tenant_id", "phone"),
        Index("ix_contacts_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    source_channel: Mapped[str | None] = mapped_column(String(30))
    source_campaign_id: Mapped[UUID | None] = mapped_column()
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    tags: Mapped[list[str]] = mapped_column(tags_type, nullable=False, default=list)
    custom_fields: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erasure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContactIdentity(Base):
    __tablename__ = "contact_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_contact_identities_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "channel_asset_id", "external_user_id",
            name="uq_contact_identities_tenant_asset_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            ondelete="CASCADE",
            name="fk_contact_identities_tenant_contact",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="CASCADE",
            name="fk_contact_identities_tenant_asset",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel_asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_metadata: Mapped[dict] = mapped_column("metadata", json_type, nullable=False, default=dict)


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_consents_tenant_identity"),
        CheckConstraint("status IN ('granted', 'revoked')", name="consent_status"),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            ondelete="CASCADE",
            name="fk_consents_tenant_contact",
        ),
        Index("ix_consents_tenant_contact_purpose", "tenant_id", "contact_id", "channel", "purpose"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "id", "channel_asset_id", "channel",
            name="uq_conversations_tenant_identity_channel",
        ),
        CheckConstraint("status IN ('open', 'pending', 'closed')", name="conversation_status"),
        CheckConstraint("ai_mode IN ('active', 'handoff_pending', 'human')", name="conversation_ai_mode"),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            ondelete="CASCADE",
            name="fk_conversations_tenant_contact",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_asset_id", "channel"],
            ["channel_assets.tenant_id", "channel_assets.id", "channel_assets.channel"],
            ondelete="RESTRICT",
            name="fk_conversations_tenant_asset_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel_asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    ai_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    control_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    assigned_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_window_id: Mapped[UUID | None] = mapped_column(index=True)
    response_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("direction IN ('inbound', 'outbound', 'system')", name="message_direction"),
        CheckConstraint("author_type IN ('contact', 'user', 'ai', 'automation', 'system')", name="message_author_type"),
        CheckConstraint(
            "status IN ('queued', 'dispatching', 'sent', 'delivered', 'read', 'failed', 'unknown', 'cancelled')",
            name="message_status",
        ),
        CheckConstraint("author_type != 'system' OR provider_message_id IS NULL", name="system_message_not_dispatched"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "channel_asset_id", "channel"],
            [
                "conversations.tenant_id",
                "conversations.id",
                "conversations.channel_asset_id",
                "conversations.channel",
            ],
            ondelete="CASCADE",
            name="fk_messages_conversation_context",
        ),
        Index(
            "uq_messages_provider_identity",
            "tenant_id",
            "channel_asset_id",
            "provider_message_id",
            unique=True,
            postgresql_where=text("provider_message_id IS NOT NULL"),
            sqlite_where=text("provider_message_id IS NOT NULL"),
        ),
        Index("ix_messages_stable_chronology", "tenant_id", "conversation_id", "occurred_at", "id"),
        Index(
            "uq_messages_client_idempotency",
            "tenant_id", "conversation_id", "client_idempotency_key",
            unique=True,
            postgresql_where=text("client_idempotency_key IS NOT NULL"),
            sqlite_where=text("client_idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel_asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    author_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body_text: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    control_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    message_metadata: Mapped[dict] = mapped_column("metadata", json_type, nullable=False, default=dict)
    client_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
