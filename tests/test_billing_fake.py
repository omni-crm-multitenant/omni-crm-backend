import json

import pytest

from app.services.billing_provider import FakeBillingProvider, fake_signature


@pytest.mark.asyncio
async def test_fake_billing_signature_and_checkout_are_deterministic() -> None:
    provider = FakeBillingProvider()
    body = json.dumps({"type": "approved"}).encode()
    event = await provider.verify_and_normalize_event({"x-signature": fake_signature(body), "x-event-id": "e1"}, body)
    assert event["event_type"] == "approved"
