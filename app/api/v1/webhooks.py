import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.services.webhook_batches import InvalidWebhookPayload, InvalidWebhookSignature, split_meta_batch
from app.services.webhook_ingress import persist_webhook_envelopes


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/meta", response_class=PlainTextResponse)
async def verify_meta_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    configured_token = get_settings().meta_webhook_verify_token
    if (
        mode != "subscribe"
        or not configured_token
        or not verify_token
        or not secrets.compare_digest(verify_token, configured_token)
        or challenge is None
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "WEBHOOK_VERIFICATION_FAILED"})
    return PlainTextResponse(challenge)


@router.post("/meta", status_code=status.HTTP_200_OK)
async def receive_meta_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    settings = get_settings()
    if not settings.meta_app_secret or not settings.meta_app_id:
        raise HTTPException(status_code=503, detail={"code": "META_WEBHOOK_NOT_CONFIGURED"})
    raw_body = await request.body()
    try:
        envelopes = split_meta_batch(
            raw_body,
            signature=request.headers.get("x-hub-signature-256"),
            app_secret=settings.meta_app_secret,
        )
    except InvalidWebhookSignature as exc:
        raise HTTPException(status_code=403, detail={"code": "WEBHOOK_SIGNATURE_INVALID"}) from exc
    except InvalidWebhookPayload as exc:
        raise HTTPException(status_code=400, detail={"code": "WEBHOOK_PAYLOAD_INVALID"}) from exc
    try:
        persisted = await persist_webhook_envelopes(session, envelopes, meta_app_id=settings.meta_app_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail={"code": "WEBHOOK_PERSISTENCE_UNAVAILABLE"}) from exc
    return {"status": "accepted", "events": len(persisted)}
