from __future__ import annotations

import json
import logging

from app.core.request_context import current_actor_id, current_request_id
from app.core.sanitization import sanitize_metadata
from app.core.tenant_context import get_current_tenant_id


class JsonContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "message": record.getMessage(), "level": record.levelname,
            "logger": record.name, "request_id": current_request_id(),
            "tenant_id": str(get_current_tenant_id()) if get_current_tenant_id() else None,
            "actor_id": str(current_actor_id()) if current_actor_id() else None,
            "result": getattr(record, "result", None),
        }
        return json.dumps(sanitize_metadata(payload), ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonContextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
