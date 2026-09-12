from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Message
from app.core.metrics import record_delivery


STATUS_ORDER = {"queued": 0, "dispatching": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 0, "unknown": 0, "cancelled": 0}


async def apply_whatsapp_delivery_status(session: AsyncSession, *, tenant_id: UUID, channel_asset_id: UUID, provider_message_id: str, status: str) -> Message | None:
    message = await session.scalar(select(Message).where(
        Message.tenant_id == tenant_id, Message.channel_asset_id == channel_asset_id,
        Message.provider_message_id == provider_message_id,
    ).with_for_update())
    if message is None:
        return None
    if status not in {"sent", "delivered", "read", "failed"}:
        raise ValueError("unsupported delivery status")
    if status != "failed" and STATUS_ORDER.get(status, 0) < STATUS_ORDER.get(message.status, 0):
        return message
    message.status = status
    record_delivery(message.channel, status)
    await session.flush()
    return message
