from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.api.v1.conversations import MessageResponse
from app.core.tenant_context import TenantContext
from app.services.authorization import AuthorizationDenied
from app.services.unknown_messages import UnknownMessageError, resolve_unknown_message


router = APIRouter(prefix="/messages", tags=["messages"])


class ResolveUnknownRequest(BaseModel):
    receipt_provider_message_id: str | None = None
    resend: bool = False
    duplicate_risk_acknowledged: bool = False


@router.post("/{message_id}/resolve-unknown", response_model=MessageResponse)
async def resolve_message(
    message_id: UUID,
    payload: ResolveUnknownRequest,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    try:
        message = await resolve_unknown_message(
            session, context=context, message_id=message_id,
            receipt_provider_message_id=payload.receipt_provider_message_id,
            resend=payload.resend,
            duplicate_risk_acknowledged=payload.duplicate_risk_acknowledged,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    except UnknownMessageError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return MessageResponse.model_validate(message, from_attributes=True)
