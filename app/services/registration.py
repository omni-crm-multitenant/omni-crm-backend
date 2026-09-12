import re
import secrets
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Membership, Tenant, User
from app.services.pipeline import create_default_pipeline


class EmailAlreadyRegisteredError(ValueError):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    tenant: Tenant
    user: User
    membership: Membership


RegistrationHook = Callable[[AsyncSession, RegistrationResult], Awaitable[None]]


def normalize_email(email: str) -> str:
    return email.strip().lower()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:120] or "empresa"


async def _unique_slug(session: AsyncSession, company_name: str) -> str:
    base = slugify(company_name)
    exists = await session.scalar(select(Tenant.id).where(Tenant.slug == base))
    if exists is None:
        return base
    return f"{base[:113].rstrip('-')}-{secrets.token_hex(3)}"


async def register_company(
    session: AsyncSession,
    company_name: str,
    admin_name: str,
    admin_email: str,
    admin_password: str,
    after_identity_created: RegistrationHook | None = None,
) -> RegistrationResult:
    email = normalize_email(admin_email)
    async with session.begin():
        existing_user = await session.scalar(select(User.id).where(User.email == email))
        if existing_user is not None:
            raise EmailAlreadyRegisteredError("EMAIL_ALREADY_REGISTERED")

        tenant = Tenant(
            name=company_name.strip(),
            slug=await _unique_slug(session, company_name),
            timezone="America/Bogota",
            locale="es-CO",
            status="active",
        )
        user = User(
            name=admin_name.strip(),
            email=email,
            password_hash=hash_password(admin_password),
            status="active",
        )
        membership = Membership(
            tenant=tenant,
            user=user,
            role="administrador",
            status="active",
            accepted_at=datetime.now(UTC),
        )
        session.add_all([tenant, user, membership])
        await session.flush()
        await create_default_pipeline(session, tenant.id)
        result = RegistrationResult(tenant=tenant, user=user, membership=membership)
        if after_identity_created is not None:
            await after_identity_created(session, result)
            await session.flush()

    return result


async def create_tenant_for_existing_user(
    session: AsyncSession,
    *,
    user_id,
    company_name: str,
) -> tuple[Tenant, Membership]:
    async with session.begin():
        user = await session.scalar(select(User).where(User.id == user_id, User.status == "active"))
        if user is None:
            raise LookupError("ACTIVE_USER_NOT_FOUND")
        tenant = Tenant(
            name=company_name.strip(),
            slug=await _unique_slug(session, company_name),
            timezone="America/Bogota",
            locale="es-CO",
            status="active",
        )
        membership = Membership(
            tenant=tenant,
            user=user,
            role="administrador",
            status="active",
            accepted_at=datetime.now(UTC),
        )
        session.add_all([tenant, membership])
        await session.flush()
        await create_default_pipeline(session, tenant.id)
    return tenant, membership
