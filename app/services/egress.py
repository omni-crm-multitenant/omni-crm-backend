from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class OutboundUrlBlocked(ValueError):
    code = "OUTBOUND_URL_BLOCKED"


def _provider_hosts() -> set[str]:
    settings = get_settings()
    hosts = {"graph.facebook.com"}
    if settings.openai_api_key:
        hosts.add("api.openai.com")
    if settings.anthropic_api_key:
        hosts.add("api.anthropic.com")
    return hosts


def validate_outbound_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise OutboundUrlBlocked("HTTPS_PROVIDER_URL_REQUIRED")
    hosts = allowed_hosts or _provider_hosts()
    if host not in {item.lower().rstrip(".") for item in hosts}:
        raise OutboundUrlBlocked("OUTBOUND_HOST_NOT_ALLOWED")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise OutboundUrlBlocked("OUTBOUND_DNS_FAILED") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise OutboundUrlBlocked("OUTBOUND_DNS_INVALID") from exc
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise OutboundUrlBlocked("OUTBOUND_PRIVATE_ADDRESS")
    return url


class HardenedHttpClient:
    def __init__(self, *, timeout: httpx.Timeout | float = 10.0, allowed_hosts: set[str] | None = None) -> None:
        self.allowed_hosts = allowed_hosts
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        )

    async def __aenter__(self) -> "HardenedHttpClient":
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.client.__aexit__(exc_type, exc_value, traceback)

    async def request(self, method: str, url: str, **kwargs):
        validate_outbound_url(url, allowed_hosts=self.allowed_hosts)
        return await self.client.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)


def hardened_http_client(*, timeout: httpx.Timeout | float = 10.0, allowed_hosts: set[str] | None = None) -> HardenedHttpClient:
    return HardenedHttpClient(timeout=timeout, allowed_hosts=allowed_hosts)
