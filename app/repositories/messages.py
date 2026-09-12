from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Message
from app.services.message_authors import MessageAuthor, validate_message_author_storage


async def create_message(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_asset_id: UUID,
    channel: str,
    direction: str,
    status: str,
    author: MessageAuthor,
    body_text: str | None = None,
    provider_message_id: str | None = None,
    occurred_at: datetime | None = None,
    message_metadata: dict | None = None,
    client_idempotency_key: str | None = None,
    client_request_hash: str | None = None,
) -> Message:
    author_fields = author.storage_fields()
    metadata = dict(message_metadata or {})
    metadata.update(author_fields.pop("message_metadata", {}))
    validate_message_author_storage(author_fields["author_type"], author_fields["author_user_id"], metadata)
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        channel_asset_id=channel_asset_id,
        channel=channel,
        direction=direction,
        status=status,
        body_text=body_text,
        provider_message_id=provider_message_id,
        occurred_at=occurred_at,
        message_metadata=metadata,
        client_idempotency_key=client_idempotency_key,
        client_request_hash=client_request_hash,
        **author_fields,
    )
    session.add(message)
    await session.flush()
    return message
