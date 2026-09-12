from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


_current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    membership_id: UUID
    user_id: UUID
    role: Literal["administrador", "supervisor", "agente_comercial"]


@dataclass(frozen=True)
class IntegrationContext:
    tenant_id: UUID
    channel_asset_id: UUID
    provider: str
    correlation_id: UUID


def get_current_tenant_id() -> UUID | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: UUID) -> Token[UUID | None]:
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token[UUID | None]) -> None:
    _current_tenant_id.reset(token)


def clear_current_tenant_id() -> None:
    _current_tenant_id.set(None)
