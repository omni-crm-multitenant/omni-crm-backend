from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.pagination import InvalidCursor, paginate
from app.core.tenant_context import TenantContext
from app.models.crm import Conversation, Message


router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationResponse(BaseModel):
    id: UUID
    contact_id: UUID
    channel_asset_id: UUID
    channel: str
    status: str
    ai_mode: str
    assigned_user_id: UUID | None
    last_message_at: datetime | None
    created_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None


class MessageResponse(BaseModel):
    id: UUID
    direction: str
    author_type: str
    author_user_id: UUID | None
    body_text: str | None
    provider_message_id: str | None
    status: str
    occurred_at: datetime
    created_at: datetime
    client_idempotency_key: str | None = None
    message_metadata: dict = Field(default_factory=dict, exclude=True)

    @computed_field
    @property
    def uncertainty(self) -> bool:
        return self.status == "unknown"

    @computed_field
    @property
    def attempt_evidence(self) -> list[dict]:
        return list(self.message_metadata.get("attempt_history", []))


class MessagePage(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None


class SendMessageRequest(BaseModel):
    body_text: str = Field(min_length=1, max_length=10000)


class AiModeRequest(BaseModel):
    mode: str


@router.post("/{conversation_id}/takeover", response_model=ConversationResponse)
async def takeover_conversation(
    conversation_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    from app.services.authorization import AuthorizationDenied
    from app.services.conversation_control import takeover_conversation as perform_takeover
    try:
        conversation = await perform_takeover(session, context=context, conversation_id=conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    return ConversationResponse.model_validate(conversation, from_attributes=True)


@router.post("/{conversation_id}/ai-mode", response_model=ConversationResponse)
async def set_ai_mode(
    conversation_id: UUID,
    payload: AiModeRequest,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    from app.services.authorization import AuthorizationDenied
    from app.services.conversation_control import set_conversation_mode
    try:
        conversation = await set_conversation_mode(session, context=context, conversation_id=conversation_id, mode=payload.mode)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc
    return ConversationResponse.model_validate(conversation, from_attributes=True)


@router.get("", response_model=ConversationPage)
async def list_conversations(
    status: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    assigned_user_id: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationPage:
    query = select(Conversation).where(Conversation.tenant_id == context.tenant_id)
    if status is not None:
        query = query.where(Conversation.status == status)
    if channel is not None:
        query = query.where(Conversation.channel == channel)
    if assigned_user_id is not None:
        query = query.where(Conversation.assigned_user_id == assigned_user_id)
    try:
        page = await paginate(session, query, cursor, limit, (Conversation.created_at, Conversation.id))
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from exc
    return ConversationPage(
        items=[ConversationResponse.model_validate(item, from_attributes=True) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: UUID,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MessagePage:
    conversation_exists = await session.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == context.tenant_id,
        )
    )
    if conversation_exists is None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND"})

    query = select(Message).where(
        Message.tenant_id == context.tenant_id,
        Message.conversation_id == conversation_id,
    )
    try:
        page = await paginate(session, query, cursor, limit, (Message.occurred_at, Message.id))
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from exc
    return MessagePage(
        items=[MessageResponse.model_validate(item, from_attributes=True) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    from app.services.authorization import AuthorizationDenied
    from app.services.send_intent import IdempotencyConflict, create_send_intent
    try:
        message = await create_send_intent(
            session, context=context, conversation_id=conversation_id, body_text=payload.body_text,
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code}) from exc
    return MessageResponse.model_validate(message, from_attributes=True)
