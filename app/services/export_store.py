from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


_exports: dict[str, tuple[datetime, dict[str, Any]]] = {}


def put_export(document: dict[str, Any], *, ttl_seconds: int = 900) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    reference = f"export:{uuid4()}"
    _exports[reference] = (expires_at, document)
    return reference, expires_at


def get_export(reference: str) -> dict[str, Any] | None:
    item = _exports.get(reference)
    if item is None:
        return None
    expires_at, document = item
    if expires_at <= datetime.now(UTC):
        _exports.pop(reference, None)
        return None
    return document
