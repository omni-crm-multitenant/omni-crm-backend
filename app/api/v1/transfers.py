from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.pagination import InvalidCursor, paginate
from app.core.tenant_context import TenantContext
from app.models.handoffs import ConversationTransfer
from app.services.authorization import AuthorizationDenied
from app.services.handoff import accept_handoff


router = APIRouter(prefix="/ai/transfers", tags=["ai-transfers"])


class TransferResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    trigger_id: UUID
    reason: str
    recipient_user_id: UUID | None
    status: str
    created_at: datetime
    accepted_at: datetime | None


class TransferPage(BaseModel):
    items: list[TransferResponse]
    next_cursor: str | None


@router.get("", response_model=TransferPage)
async def list_transfers(
    status_filter: str | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> TransferPage:
    query = select(ConversationTransfer).where(ConversationTransfer.tenant_id == context.tenant_id)
    if status_filter:
        query = query.where(ConversationTransfer.status == status_filter)
    try:
        page = await paginate(session, query, cursor, limit, (ConversationTransfer.created_at, ConversationTransfer.id))
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from exc
    return TransferPage(
        items=[TransferResponse.model_validate(item, from_attributes=True) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/{transfer_id}/accept", response_model=TransferResponse)
async def accept_transfer(
    transfer_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> TransferResponse:
    try:
        transfer = await accept_handoff(session, transfer_id=transfer_id, context=context)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    return TransferResponse.model_validate(transfer, from_attributes=True)
