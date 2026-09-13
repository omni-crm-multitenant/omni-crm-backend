from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.crm import CustomFieldDefinition
from app.services.audit import write_audit_event
from app.api.dependencies import require_roles
from app.services.custom_fields import (
    ExplicitValueMigrationRequired,
    change_custom_field_type,
    custom_field_has_values,
)


router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])

EntityType = Literal["contact", "opportunity"]
FieldType = Literal["text", "number", "boolean", "date", "select", "multiselect"]


def _validate_options(field_type: str, options: list[str] | None) -> list[str] | None:
    if field_type in {"select", "multiselect"}:
        normalized = [item.strip() for item in options or [] if item.strip()]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("select fields require unique non-empty options")
        return normalized
    if options:
        raise ValueError("options are only valid for select fields")
    return None


class CustomFieldCreate(BaseModel):
    entity_type: EntityType
    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    field_type: FieldType
    options: list[str] | None = None
    required: bool = False

    @model_validator(mode="after")
    def valid_options(self):
        self.options = _validate_options(self.field_type, self.options)
        return self


class CustomFieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    field_type: FieldType | None = None
    options: list[str] | None = None
    required: bool | None = None


class CustomFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: EntityType
    name: str
    field_type: FieldType
    options: list[str] | None
    required: bool


async def _owned_definition(
    session: AsyncSession,
    tenant_id: UUID,
    definition_id: UUID,
) -> CustomFieldDefinition:
    definition = await session.scalar(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == definition_id,
            CustomFieldDefinition.tenant_id == tenant_id,
        )
    )
    if definition is None:
        raise HTTPException(status_code=404, detail={"code": "CUSTOM_FIELD_NOT_FOUND"})
    return definition


@router.get("", response_model=list[CustomFieldResponse])
async def list_custom_fields(
    entity_type: EntityType | None = None,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[CustomFieldDefinition]:
    statement = select(CustomFieldDefinition).where(CustomFieldDefinition.tenant_id == context.tenant_id)
    if entity_type is not None:
        statement = statement.where(CustomFieldDefinition.entity_type == entity_type)
    return list(await session.scalars(statement.order_by(CustomFieldDefinition.entity_type, CustomFieldDefinition.name)))


@router.get("/{definition_id}", response_model=CustomFieldResponse)
async def get_custom_field(
    definition_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> CustomFieldDefinition:
    return await _owned_definition(session, context.tenant_id, definition_id)


@router.post("", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    payload: CustomFieldCreate,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> CustomFieldDefinition:
    definition = CustomFieldDefinition(
        tenant_id=context.tenant_id,
        entity_type=payload.entity_type,
        name=payload.name,
        field_type=payload.field_type,
        options=payload.options,
        required=payload.required,
    )
    session.add(definition)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"code": "CUSTOM_FIELD_ALREADY_EXISTS"}) from exc
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="custom_field.created",
        resource_type="custom_field_definition",
        resource_id=definition.id,
        metadata={"entity_type": definition.entity_type, "name": definition.name},
    )
    return definition


@router.patch("/{definition_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    definition_id: UUID,
    payload: CustomFieldUpdate,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> CustomFieldDefinition:
    definition = await _owned_definition(session, context.tenant_id, definition_id)
    before = {
        "name": definition.name,
        "field_type": definition.field_type,
        "options": definition.options,
        "required": definition.required,
    }
    next_type = payload.field_type or definition.field_type
    if "options" in payload.model_fields_set:
        next_options = payload.options
    elif next_type != definition.field_type:
        next_options = None
    else:
        next_options = definition.options
    try:
        normalized_options = _validate_options(next_type, next_options)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CUSTOM_FIELD_OPTIONS"}) from exc
    try:
        await change_custom_field_type(session, definition, next_type)
    except ExplicitValueMigrationRequired as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    if payload.name is not None:
        definition.name = payload.name
    definition.options = normalized_options
    if payload.required is not None:
        definition.required = payload.required
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"code": "CUSTOM_FIELD_ALREADY_EXISTS"}) from exc
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="custom_field.updated",
        resource_type="custom_field_definition",
        resource_id=definition.id,
        metadata={
            "before": before,
            "after": {
                "name": definition.name,
                "field_type": definition.field_type,
                "options": definition.options,
                "required": definition.required,
            },
        },
    )
    return definition


@router.delete("/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_field(
    definition_id: UUID,
    confirm_values: bool = Query(default=False),
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    definition = await _owned_definition(session, context.tenant_id, definition_id)
    if await custom_field_has_values(session, definition) and not confirm_values:
        raise HTTPException(status_code=409, detail={"code": "CUSTOM_FIELD_VALUES_EXIST"})
    metadata = {"entity_type": definition.entity_type, "name": definition.name, "confirmed": confirm_values}
    await session.delete(definition)
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="custom_field.deleted",
        resource_type="custom_field_definition",
        resource_id=definition.id,
        metadata=metadata,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
