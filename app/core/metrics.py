from __future__ import annotations

from collections import defaultdict
from threading import Lock


_lock = Lock()
http_requests_total: dict[tuple[str, int], int] = defaultdict(int)
http_request_latency_ms: dict[str, list[float]] = defaultdict(list)
queue_depth: dict[str, int] = defaultdict(int)
worker_outcomes: dict[tuple[str, str], int] = defaultdict(int)
delivery_outcomes: dict[tuple[str, str], int] = defaultdict(int)
ai_token_usage: dict[tuple[str, str, str], int] = defaultdict(int)


def record_http_request(route: str, status_code: int, elapsed_ms: float) -> None:
    with _lock:
        http_requests_total[(route, status_code)] += 1
        http_request_latency_ms[route].append(elapsed_ms)


def snapshot_metrics() -> dict:
    with _lock:
        return {
            "http_requests_total": {f"{route}|{status}": count for (route, status), count in http_requests_total.items()},
            "http_request_latency_ms": {route: values[-1000:] for route, values in http_request_latency_ms.items()},
            "queue_depth": dict(queue_depth),
            "worker_outcomes": {f"{job}|{status}": count for (job, status), count in worker_outcomes.items()},
            "delivery_outcomes": {f"{channel}|{status}": count for (channel, status), count in delivery_outcomes.items()},
            "ai_token_usage": {f"{tenant}|{provider}|{model}": count for (tenant, provider, model), count in ai_token_usage.items()},
        }


def record_queue(name: str, depth: int) -> None:
    with _lock: queue_depth[name] = max(0, depth)


def record_worker(name: str, status: str) -> None:
    with _lock: worker_outcomes[(name, status)] += 1


def record_delivery(channel: str, status: str) -> None:
    with _lock: delivery_outcomes[(channel, status)] += 1


def record_ai_tokens(tenant_id: str, provider: str, model: str, tokens: int) -> None:
    with _lock: ai_token_usage[(tenant_id, provider, model)] += max(0, tokens)
