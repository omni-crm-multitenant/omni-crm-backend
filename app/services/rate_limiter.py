from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


SLIDING_WINDOW_LUA = """
local now = redis.call('TIME')[1]
local cutoff = now - tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[2]) then
  local first = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')[2]
  return {0, tonumber(ARGV[1]) - (now - first)}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
return {1, 0}
"""


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_after: int


class RedisSlidingWindowLimiter:
    def __init__(self, redis):
        self.redis = redis

    async def check_limit(self, key: str, limit: int, window_seconds: int) -> LimitResult:
        result = await self.redis.eval(
            SLIDING_WINDOW_LUA, 1, key, window_seconds, limit, f"{time.time_ns()}"
        )
        return LimitResult(bool(result[0]), max(0, int(result[1])))


class InMemoryLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)

    async def check_limit(self, key: str, limit: int, window_seconds: int) -> LimitResult:
        now = time.monotonic()
        events = self._events[key]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            return LimitResult(False, max(1, int(events[0] + window_seconds - now)))
        events.append(now)
        return LimitResult(True, 0)


PLAN_LIMITS = {
    "free": {"http_per_minute": 60, "provider_per_minute": 20},
    "starter": {"http_per_minute": 120, "provider_per_minute": 60},
    "pro": {"http_per_minute": 600, "provider_per_minute": 240},
}


def limits_for_plan(plan_code: str | None) -> dict[str, int]:
    return PLAN_LIMITS.get(plan_code or "free", PLAN_LIMITS["free"])


async def check_provider_limit(limiter, *, tenant_id: str, provider: str, plan_code: str | None = None) -> LimitResult:
    limits = limits_for_plan(plan_code)
    return await limiter.check_limit(f"provider:{tenant_id}:{provider}", limits["provider_per_minute"], 60)
