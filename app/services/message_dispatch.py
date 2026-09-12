from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Conversation, Message
from app.models.identity import ChannelAsset
from app.services.channel_adapters import InstagramAdapter, MessengerAdapter, WhatsAppAdapter
from app.services.credentials import get_credential_store
from app.services.message_attempts import finish_message_attempt, start_message_attempt
from app.services.kpi import close_response_window
from app.services.conversation_timers import cancel_unanswered_timers, schedule_unanswered_timers


async def dispatch_queued_message(session: AsyncSession, *, tenant_id: UUID, message_id: UUID) -> Message | None:
    message = await session.scalar(select(Message).where(
        Message.id == message_id, Message.tenant_id == tenant_id, Message.status == "queued",
    ).with_for_update())
    if message is None:
        return None
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == message.conversation_id, Conversation.tenant_id == tenant_id,
    ).with_for_update())
    asset = await session.scalar(select(ChannelAsset).where(
        ChannelAsset.id == message.channel_asset_id, ChannelAsset.tenant_id == tenant_id,
    ))
    if conversation is None or asset is None:
        message.status = "failed"
        await session.flush()
        return message
    expected_version = message.message_metadata.get("control_version")
    if message.author_type == "ai" and (
        conversation.ai_mode != "active" or
        (expected_version is not None and expected_version != conversation.control_version)
    ):
        message.status = "cancelled"
        message.message_metadata = {**message.message_metadata, "cancel_reason": "CONTROL_VERSION_FENCE"}
        await session.flush()
        return message
    adapter_type = {"whatsapp": WhatsAppAdapter, "instagram": InstagramAdapter, "messenger": MessengerAdapter}.get(asset.channel)
    if adapter_type is None:
        message.status = "failed"
        await session.flush()
        return message
    message.status = "dispatching"
    attempt = await start_message_attempt(session, tenant_id=tenant_id, message_id=message.id)
    await session.flush()
    try:
        result = await asyncio.wait_for(
            adapter_type(get_credential_store()).send_text(asset, str(conversation.contact_id), message.body_text or ""),
            timeout=15,
        )
    except asyncio.TimeoutError:
        message.status = "unknown"
        await finish_message_attempt(session, attempt, status="unknown", error_code="PROVIDER_TIMEOUT")
    except Exception:
        message.status = "failed"
        await finish_message_attempt(session, attempt, status="rejected", error_code="PROVIDER_REJECTED")
    else:
        message.status = result.status
        message.provider_message_id = result.provider_message_id
        await finish_message_attempt(
            session, attempt,
            status="accepted" if result.status in {"sent", "delivered", "read"} else "rejected",
            provider_message_id=result.provider_message_id,
        )
        if result.status in {"sent", "delivered", "read"}:
            await close_response_window(session, message=message)
            await cancel_unanswered_timers(session, tenant_id=message.tenant_id, conversation_id=message.conversation_id, trigger_type="team_unanswered")
            await schedule_unanswered_timers(session, conversation=conversation, direction="outbound", message=message)
    history = list(message.message_metadata.get("attempt_history", []))
    history.append({
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "provider_message_id": attempt.provider_message_id,
        "error_code": attempt.error_code,
    })
    message.message_metadata = {**message.message_metadata, "attempt_history": history}
    await session.flush()
    return message
