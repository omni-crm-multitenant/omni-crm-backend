from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Contact, Conversation
from app.services.audit import write_audit_event
from app.services.custom_fields import validate_custom_field_payload
from app.services.normalization import normalize_email, normalize_phone


class ContactQualificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    custom_fields: dict = Field(default_factory=dict)


def _tool_decorator(function):
    function.name = function.__name__
    function.description = function.__doc__ or ""
    return function


def build_update_contact_qualification_tool(
    session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, ai_run_id: UUID,
):
    @_tool_decorator
    async def update_contact_qualification(fields: dict) -> dict:
        """Update only qualification fields on the conversation's contact."""
        update = ContactQualificationUpdate.model_validate(fields)
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ))
        if conversation is None:
            raise LookupError("CONVERSATION_NOT_FOUND")
        contact = await session.scalar(select(Contact).where(
            Contact.id == conversation.contact_id, Contact.tenant_id == tenant_id,
        ).with_for_update())
        if contact is None:
            raise LookupError("CONTACT_NOT_FOUND")
        values = update.model_dump(exclude_unset=True)
        custom_fields = values.pop("custom_fields", {})
        await validate_custom_field_payload(
            session, tenant_id=tenant_id, entity_type="contact",
            values=custom_fields, require_all=False,
        )
        if "phone" in values and values["phone"]:
            values["phone"] = normalize_phone(values["phone"])
        if "email" in values and values["email"]:
            values["email"] = normalize_email(values["email"])
        if custom_fields:
            contact.custom_fields = {**contact.custom_fields, **custom_fields}
        for key, value in values.items():
            setattr(contact, key, value)
        changed = {key: value for key, value in values.items()}
        if custom_fields:
            changed["custom_fields"] = custom_fields
        await write_audit_event(
            session, tenant_id=tenant_id, actor_type="ai", action="contact.qualification_updated",
            resource_type="contact", resource_id=contact.id,
            metadata={"ai_run_id": str(ai_run_id), "fields": sorted(changed)},
        )
        await session.flush()
        return {"contact_id": str(contact.id), "changed_fields": sorted(changed)}

    return update_contact_qualification
