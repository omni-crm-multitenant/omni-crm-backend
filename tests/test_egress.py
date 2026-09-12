import socket

import pytest

from app.services.egress import HardenedHttpClient, OutboundUrlBlocked, validate_outbound_url


def test_egress_rejects_private_dns_result(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))])
    with pytest.raises(OutboundUrlBlocked, match="OUTBOUND_PRIVATE_ADDRESS"):
        validate_outbound_url("https://graph.facebook.com/resource")


def test_egress_rejects_localhost_and_non_https() -> None:
    with pytest.raises(OutboundUrlBlocked, match="OUTBOUND_HOST_NOT_ALLOWED"):
        validate_outbound_url("https://localhost/resource")
    with pytest.raises(OutboundUrlBlocked, match="HTTPS_PROVIDER_URL_REQUIRED"):
        validate_outbound_url("http://graph.facebook.com/resource")


def test_hardened_client_disables_redirects() -> None:
    client = HardenedHttpClient()
    assert client.client.follow_redirects is False
