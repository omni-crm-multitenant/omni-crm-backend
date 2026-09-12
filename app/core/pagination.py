from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import and_, or_, Select
from sqlalchemy.ext.asyncio import AsyncSession


class InvalidCursor(ValueError):
    pass


@dataclass(frozen=True)
class CursorPage:
    items: list[Any]
    next_cursor: str | None


def encode_cursor(occurred_at: datetime, item_id: UUID) -> str:
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    payload = json.dumps(
        {"occurred_at": occurred_at.astimezone(UTC).isoformat(), "id": str(item_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        occurred_at = datetime.fromisoformat(value["occurred_at"])
        item_id = UUID(value["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidCursor("invalid cursor") from exc
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at, item_id


async def paginate(
    session: AsyncSession,
    query: Select,
    cursor: str | None,
    limit: int,
    order_by: Sequence[Any],
) -> CursorPage:
    """Fetch stable pages ordered by occurred_at and id."""
    if len(order_by) != 2 or not 1 <= limit <= 100:
        raise ValueError("order_by needs occurred_at and id; limit must be between 1 and 100")
    occurred_at_column, id_column = order_by
    statement = query.order_by(occurred_at_column.asc(), id_column.asc()).limit(limit + 1)
    if cursor:
        occurred_at, item_id = decode_cursor(cursor)
        if not getattr(occurred_at_column.type, "timezone", False):
            occurred_at = occurred_at.replace(tzinfo=None)
        statement = statement.where(
            or_(
                occurred_at_column > occurred_at,
                and_(occurred_at_column == occurred_at, id_column > item_id),
            )
        )
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(getattr(last, occurred_at_column.key), getattr(last, id_column.key))
    return CursorPage(items=items, next_cursor=next_cursor)
