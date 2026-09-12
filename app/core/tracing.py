from __future__ import annotations

import inspect
import hashlib
from functools import wraps
from time import perf_counter
from typing import Any

from app.core.request_context import current_actor_id, current_request_id
from app.core.sanitization import sanitize_metadata
from app.core.tenant_context import get_current_tenant_id


spans: list[dict[str, Any]] = []


def traced(node_name: str):
    def decorator(function):
        @wraps(function)
        async def wrapper(*args, **kwargs):
            started = perf_counter()
            result = "success"
            state = args[0] if args and hasattr(args[0], "messages") else None
            try:
                return await function(*args, **kwargs)
            except Exception:
                result = "error"
                raise
            finally:
                spans.append(sanitize_metadata({
                    "node": node_name, "result": result,
                    "started_at": started, "elapsed_ms": (perf_counter() - started) * 1000,
                    "ai_run_id": str(getattr(state, "ai_run_id", None)) if state else None,
                    "input_sha256": hashlib.sha256(str(getattr(state, "messages", "")).encode()).hexdigest() if state else None,
                    "request_id": current_request_id(),
                    "tenant_id": str(get_current_tenant_id()) if get_current_tenant_id() else None,
                    "actor_id": str(current_actor_id()) if current_actor_id() else None,
                }))
        return wrapper
    return decorator
