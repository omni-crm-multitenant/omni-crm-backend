PUBLIC_ENDPOINTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("POST", "/api/v1/auth/register"),
        ("GET", "/api/v1/auth/verify-email"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/forgot-password"),
        ("POST", "/api/v1/auth/reset-password"),
        ("POST", "/api/v1/auth/mfa/verify"),
        ("GET", "/api/v1/channel-assets/connect/callback"),
        ("GET", "/api/v1/webhooks/meta"),
        ("POST", "/api/v1/webhooks/meta"),
        ("GET", "/api/v1/invitations/{token}"),
        ("POST", "/api/v1/invitations/{token}/accept"),
    }
)


def is_public_endpoint(method: str, path: str) -> bool:
    return (method.upper(), path) in PUBLIC_ENDPOINTS
