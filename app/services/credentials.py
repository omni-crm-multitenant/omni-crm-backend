from __future__ import annotations

import secrets
from functools import lru_cache

from app.domain.credentials import CredentialStore


class CredentialNotFound(LookupError):
    pass


class InMemoryCredentialStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def put(self, secret: str) -> str:
        reference = f"memory://{secrets.token_urlsafe(18)}"
        self._values[reference] = secret
        return reference

    async def get(self, reference: str) -> str:
        try:
            return self._values[reference]
        except KeyError as exc:
            raise CredentialNotFound(reference) from exc

    async def delete(self, reference: str) -> None:
        self._values.pop(reference, None)


@lru_cache
def get_credential_store() -> CredentialStore:
    """Return local credential adapter until durable secret storage is configured."""
    return InMemoryCredentialStore()


__all__ = ["CredentialNotFound", "CredentialStore", "InMemoryCredentialStore", "get_credential_store"]
