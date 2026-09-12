from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_id_var: ContextVar[UUID | None] = ContextVar("actor_id", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


def current_actor_id() -> UUID | None:
    return actor_id_var.get()
