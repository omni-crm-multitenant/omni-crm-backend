from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any, Protocol
from uuid import UUID, uuid5, NAMESPACE_URL


class ProviderNotEnabled(RuntimeError):
    code = "PROVIDER_NOT_ENABLED"


@dataclass(frozen=True)
class Checkout:
    reference: str
    url: str


class BillingProvider(Protocol):
    async def create_checkout(self, tenant_id: UUID, plan_code: str, request_id: str) -> Checkout: ...
    async def get_subscription(self, reference: str) -> dict[str, Any]: ...
    async def cancel_subscription(self, reference: str) -> None: ...
    async def verify_and_normalize_event(self, headers: dict[str, str], body: bytes) -> dict[str, Any]: ...


class FakeBillingProvider:
    secret = "synthetic-billing-secret"
    async def create_checkout(self, tenant_id: UUID, plan_code: str, request_id: str) -> Checkout:
        reference = str(uuid5(NAMESPACE_URL, f"{tenant_id}:{plan_code}:{request_id}"))
        return Checkout(reference=reference, url=f"https://billing.local/checkout/{reference}")

    async def get_subscription(self, reference: str) -> dict[str, Any]:
        return {"reference": reference, "status": "pending"}

    async def cancel_subscription(self, reference: str) -> None:
        return None

    async def verify_and_normalize_event(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(headers.get("x-signature", ""), expected):
            raise ValueError("BILLING_SIGNATURE_INVALID")
        payload = json.loads(body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("BILLING_PAYLOAD_INVALID")
        return {"provider_event_id": headers.get("x-event-id", "fake-event"), "event_type": str(payload.get("type", "test")), "payload": payload}


def fake_signature(body: bytes) -> str:
    return hmac.new(FakeBillingProvider.secret.encode(), body, hashlib.sha256).hexdigest()


class DisabledLiveBillingProvider:
    async def create_checkout(self, *args, **kwargs): raise ProviderNotEnabled()
    async def get_subscription(self, *args, **kwargs): raise ProviderNotEnabled()
    async def cancel_subscription(self, *args, **kwargs): raise ProviderNotEnabled()
    async def verify_and_normalize_event(self, *args, **kwargs): raise ProviderNotEnabled()


def billing_provider(*, live_enabled: bool = False) -> BillingProvider:
    return FakeBillingProvider() if not live_enabled else DisabledLiveBillingProvider()
