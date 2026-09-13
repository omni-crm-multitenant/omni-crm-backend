from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contacts import ContactResolution, find_or_create_contact_with_decision


@dataclass(frozen=True)
class LeadNotification:
    leadgen_id: str
    page_id: str | None
    ad_id: str | None
    form_id: str | None


def parse_lead_notification(payload: dict[str, Any]) -> LeadNotification:
    value = payload.get("value", payload)
    if not isinstance(value, dict):
        raise ValueError("lead notification value must be an object")
    leadgen_id = value.get("leadgen_id") or value.get("lead_id")
    if not leadgen_id:
        raise ValueError("lead notification lacks leadgen_id")
    return LeadNotification(
        leadgen_id=str(leadgen_id),
        page_id=str(value["page_id"]) if value.get("page_id") else None,
        ad_id=str(value["ad_id"]) if value.get("ad_id") else None,
        form_id=str(value["form_id"]) if value.get("form_id") else None,
    )


async def fetch_lead_detail(client: Any, notification: LeadNotification, access_token: str) -> dict[str, Any]:
    return await client.get(
        f"/{notification.leadgen_id}", access_token=access_token,
        params={"fields": "field_data,created_time,ad_id,form_id"},
    )


async def ingest_lead(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    channel: str,
    channel_asset_id: UUID,
    external_user_id: str,
    notification: LeadNotification,
    client: Any,
    access_token: str,
) -> ContactResolution:
    detail = await fetch_lead_detail(client, notification, access_token)
    fields = {item.get("name"): item.get("values", [None])[0] for item in detail.get("field_data", []) if item.get("name")}
    resolution = await find_or_create_contact_with_decision(
        session, tenant_id=tenant_id, channel=channel, channel_asset_id=channel_asset_id,
        external_user_id=external_user_id, phone=fields.get("phone"), email=fields.get("email"),
        name=fields.get("full_name") or fields.get("name"),
    )
    from app.models.lead import LeadReference
    from app.models.marketing import Campaign
    from app.models.attribution import Attribution
    from app.services.attribution import classify_attribution
    campaign = None
    if notification.ad_id:
        campaign = await session.scalar(select(Campaign).where(
            Campaign.tenant_id == tenant_id, Campaign.external_id == notification.ad_id,
        ))
    if campaign is not None:
        resolution.contact.source_campaign_id = campaign.id
    raw_hash = hashlib.sha256(json.dumps(detail, sort_keys=True, default=str).encode()).hexdigest()
    session.add(LeadReference(
        tenant_id=tenant_id, contact_id=resolution.contact.id,
        leadgen_id=notification.leadgen_id, payload_hash=raw_hash,
        lead_metadata={"ad_id": notification.ad_id, "form_id": notification.form_id},
    ))
    campaign_id = campaign.id if campaign is not None else None
    session.add(Attribution(
        tenant_id=tenant_id, contact_id=resolution.contact.id,
        campaign_id=campaign_id, source="meta_lead",
        confidence=classify_attribution(campaign_id, None, None),
        raw_metadata={"leadgen_id": notification.leadgen_id, "ad_id": notification.ad_id, "form_id": notification.form_id},
    ))
    await session.flush()
    return resolution
