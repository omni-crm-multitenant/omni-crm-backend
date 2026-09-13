from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.application.contacts import (
    ContactListQuery,
    CreateContactCommand,
    UpdateContactCommand,
    create_contact as create_contact_case,
    list_contacts as list_contacts_case,
    update_contact as update_contact_case,
)
from app.core.tenant_context import TenantContext
from app.models.crm import Consent, Contact, ContactIdentity
from app.models.merge_candidates import ContactMergeCandidate
from app.models.operations import TenantSettings
from app.services.audit import write_audit_event
from app.api.dependencies import require_roles
from app.services.custom_fields import CustomFieldValidationError
from app.services.contact_privacy import logically_erase_contact
from app.services.jobs import create_job

from app.core.pagination import InvalidCursor
from app.workers.contact_privacy_tasks import export_contact


router = APIRouter(prefix="/contacts", tags=["contacts"])


class ConsentRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=30)
    purpose: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=120)


class OptOutRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=30)
    purpose: str = Field(min_length=1, max_length=80)


class ConsentResponse(BaseModel):
    id: UUID
    contact_id: UUID
    channel: str
    purpose: str
    status: str
    source: str
    captured_at: datetime
    revoked_at: datetime | None


class MergeCandidateResponse(BaseModel):
    id: UUID
    contact_id_a: UUID
    contact_id_b: UUID
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class MergeResolutionRequest(BaseModel):
    action: str
    keep_contact_id: UUID | None = None


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    source_channel: str | None = Field(default=None, max_length=30)
    owner_user_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    owner_user_id: UUID | None = None
    tags: list[str] | None = None
    custom_fields: dict | None = None


class ContactResponse(BaseModel):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    source_channel: str | None
    owner_user_id: UUID | None
    status: str
    tags: list[str]
    custom_fields: dict
    created_at: datetime
    updated_at: datetime


class ContactPage(BaseModel):
    items: list[ContactResponse]
    next_cursor: str | None


class IdentityResponse(BaseModel):
    id: UUID
    channel_asset_id: UUID
    external_user_id: str
    display_name: str | None
    last_seen_at: datetime | None


class ContactJobResponse(BaseModel):
    job_id: str
    status: str


class ErasureResponse(BaseModel):
    contact_id: UUID
    status: str
    erasure_requested_at: datetime


async def _contact_or_404(
    session: AsyncSession, tenant_id: UUID, contact_id: UUID
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
            Contact.status != "deleted",
            Contact.deleted_at.is_(None),
        )
    )
    if contact is None:
        raise HTTPException(status_code=404, detail={"code": "CONTACT_NOT_FOUND"})
    return contact


@router.get(
    "/merge-candidates",
    response_model=list[MergeCandidateResponse],
    include_in_schema=False,
)
async def list_merge_candidates_before_contact_id(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[MergeCandidateResponse]:
    rows = list(
        (
            await session.scalars(
                select(ContactMergeCandidate)
                .where(
                    ContactMergeCandidate.tenant_id == context.tenant_id,
                    ContactMergeCandidate.status == "pending",
                )
                .order_by(ContactMergeCandidate.created_at.asc())
            )
        ).all()
    )
    return [
        MergeCandidateResponse.model_validate(row, from_attributes=True) for row in rows
    ]


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    context: TenantContext = Depends(require_roles("supervisor", "administrador")),
    session: AsyncSession = Depends(get_session),
) -> ContactResponse:
    try:
        contact = await create_contact_case(
            session,
            context=context,
            command=CreateContactCommand(**payload.model_dump()),
        )
    except CustomFieldValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CUSTOM_FIELD",
                "field": exc.field_name,
                "reason": exc.reason,
            },
        ) from exc
    return ContactResponse.model_validate(contact, from_attributes=True)


@router.get("", response_model=ContactPage)
async def list_contacts(
    status_filter: str | None = Query(default=None, alias="status"),
    owner_user_id: UUID | None = None,
    tag: str | None = None,
    source_channel: str | None = None,
    custom_field: str | None = None,
    custom_value: str | None = None,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ContactPage:
    try:
        page = await list_contacts_case(
            session,
            context=context,
            query=ContactListQuery(
                status=status_filter,
                owner_user_id=owner_user_id,
                tag=tag,
                source_channel=source_channel,
                custom_field=custom_field,
                custom_value=custom_value,
                cursor=cursor,
                limit=limit,
            ),
        )
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from exc
    return ContactPage(
        items=[
            ContactResponse.model_validate(row, from_attributes=True)
            for row in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/{contact_id}/export",
    response_model=ContactJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_contact_data(
    contact_id: UUID,
    response: Response,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> ContactJobResponse:
    await _contact_or_404(session, context.tenant_id, contact_id)
    job_id = await create_job(session, context.tenant_id, "contact_export")
    export_contact.delay(str(context.tenant_id), str(contact_id), str(job_id))
    response.headers["Location"] = f"/api/v1/jobs/{job_id}"
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.export_requested",
        resource_type="contact",
        resource_id=contact_id,
        metadata={"job_id": str(job_id)},
    )
    return ContactJobResponse(job_id=str(job_id), status="queued")


@router.post("/{contact_id}/erase", response_model=ErasureResponse)
async def erase_contact(
    contact_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> ErasureResponse:
    try:
        contact = await logically_erase_contact(
            session, tenant_id=context.tenant_id, contact_id=contact_id
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "CONTACT_NOT_FOUND"}
        ) from exc
    settings = await session.get(TenantSettings, context.tenant_id)
    retention_days = int(
        ((settings.contact_info if settings else {}) or {}).get("retention_days", 365)
    )
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.erasure_requested",
        resource_type="contact",
        resource_id=contact_id,
        metadata={"retention_days": retention_days},
    )
    assert contact.erasure_requested_at is not None
    return ErasureResponse(
        contact_id=contact.id,
        status="deleted",
        erasure_requested_at=contact.erasure_requested_at,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ContactResponse:
    contact = await _contact_or_404(session, context.tenant_id, contact_id)
    return ContactResponse.model_validate(contact, from_attributes=True)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    context: TenantContext = Depends(require_roles("supervisor", "administrador")),
    session: AsyncSession = Depends(get_session),
) -> ContactResponse:
    contact = await _contact_or_404(session, context.tenant_id, contact_id)
    try:
        contact = await update_contact_case(
            session,
            context=context,
            contact=contact,
            command=UpdateContactCommand(payload.model_dump(exclude_unset=True)),
        )
    except CustomFieldValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CUSTOM_FIELD",
                "field": exc.field_name,
                "reason": exc.reason,
            },
        ) from exc
    return ContactResponse.model_validate(contact, from_attributes=True)


@router.delete(
    "/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_contact(
    contact_id: UUID,
    context: TenantContext = Depends(require_roles("supervisor", "administrador")),
    session: AsyncSession = Depends(get_session),
) -> None:
    contact = await _contact_or_404(session, context.tenant_id, contact_id)
    contact.status = "deleted"
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.deleted",
        resource_type="contact",
        resource_id=contact.id,
    )
    await session.flush()


@router.get("/{contact_id}/identities", response_model=list[IdentityResponse])
async def list_contact_identities(
    contact_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[IdentityResponse]:
    await _contact_or_404(session, context.tenant_id, contact_id)
    rows = list(
        (
            await session.scalars(
                select(ContactIdentity)
                .where(
                    ContactIdentity.tenant_id == context.tenant_id,
                    ContactIdentity.contact_id == contact_id,
                )
                .order_by(ContactIdentity.id)
            )
        ).all()
    )
    return [IdentityResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post(
    "/{contact_id}/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_consent(
    contact_id: UUID,
    payload: ConsentRequest,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConsentResponse:
    await _contact_or_404(session, context.tenant_id, contact_id)
    consent = Consent(
        tenant_id=context.tenant_id,
        contact_id=contact_id,
        channel=payload.channel,
        purpose=payload.purpose,
        status="granted",
        source=payload.source,
    )
    session.add(consent)
    await session.flush()
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.consent_granted",
        resource_type="consent",
        resource_id=consent.id,
        metadata={
            "contact_id": contact_id,
            "channel": payload.channel,
            "purpose": payload.purpose,
        },
    )
    return ConsentResponse.model_validate(consent, from_attributes=True)


@router.post(
    "/{contact_id}/opt-out",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def revoke_consent(
    contact_id: UUID,
    payload: OptOutRequest,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConsentResponse:
    await _contact_or_404(session, context.tenant_id, contact_id)
    revoked_at = datetime.now(UTC)
    consent = Consent(
        tenant_id=context.tenant_id,
        contact_id=contact_id,
        channel=payload.channel,
        purpose=payload.purpose,
        status="revoked",
        source="opt_out",
        captured_at=revoked_at,
        revoked_at=revoked_at,
    )
    session.add(consent)
    await session.flush()
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.consent_revoked",
        resource_type="consent",
        resource_id=consent.id,
        metadata={
            "contact_id": contact_id,
            "channel": payload.channel,
            "purpose": payload.purpose,
        },
    )
    return ConsentResponse.model_validate(consent, from_attributes=True)


@router.get("/merge-candidates", response_model=list[MergeCandidateResponse])
async def list_merge_candidates(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[MergeCandidateResponse]:
    rows = list(
        (
            await session.scalars(
                select(ContactMergeCandidate)
                .where(
                    ContactMergeCandidate.tenant_id == context.tenant_id,
                    ContactMergeCandidate.status == "pending",
                )
                .order_by(ContactMergeCandidate.created_at.asc())
            )
        ).all()
    )
    return [
        MergeCandidateResponse.model_validate(row, from_attributes=True) for row in rows
    ]


@router.post(
    "/merge-candidates/{candidate_id}/resolve", response_model=MergeCandidateResponse
)
async def resolve_merge_candidate(
    candidate_id: UUID,
    payload: MergeResolutionRequest,
    context: TenantContext = Depends(require_roles("supervisor", "administrador")),
    session: AsyncSession = Depends(get_session),
) -> MergeCandidateResponse:
    candidate = await session.scalar(
        select(ContactMergeCandidate)
        .where(
            ContactMergeCandidate.id == candidate_id,
            ContactMergeCandidate.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if candidate is None or candidate.status != "pending":
        raise HTTPException(
            status_code=404, detail={"code": "MERGE_CANDIDATE_NOT_FOUND"}
        )
    if payload.action not in {"merge", "dismiss"}:
        raise HTTPException(status_code=422, detail={"code": "INVALID_MERGE_ACTION"})
    if payload.action == "merge":
        keep_id = payload.keep_contact_id or candidate.contact_id_a
        drop_id = (
            candidate.contact_id_b
            if keep_id == candidate.contact_id_a
            else candidate.contact_id_a
        )
        keep = await session.scalar(
            select(Contact)
            .where(Contact.id == keep_id, Contact.tenant_id == context.tenant_id)
            .with_for_update()
        )
        drop = await session.scalar(
            select(Contact)
            .where(Contact.id == drop_id, Contact.tenant_id == context.tenant_id)
            .with_for_update()
        )
        if keep is None or drop is None:
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_MERGE_CONTACTS"}
            )
        identities = list(
            (
                await session.scalars(
                    select(ContactIdentity).where(
                        ContactIdentity.tenant_id == context.tenant_id,
                        ContactIdentity.contact_id == drop.id,
                    )
                )
            ).all()
        )
        for identity in identities:
            identity.contact_id = keep.id
        keep.phone = keep.phone or drop.phone
        keep.email = keep.email or drop.email
        keep.tags = list(dict.fromkeys([*(keep.tags or []), *(drop.tags or [])]))
        drop.status = "deleted"
        candidate.status = "merged"
    else:
        candidate.status = "dismissed"
    candidate.resolved_at = datetime.now(UTC)
    candidate.resolved_by_user_id = context.user_id
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action=f"contact.merge_candidate.{payload.action}",
        resource_type="contact_merge_candidate",
        resource_id=candidate.id,
        metadata={"keep_contact_id": payload.keep_contact_id},
    )
    await session.flush()
    return MergeCandidateResponse.model_validate(candidate, from_attributes=True)
