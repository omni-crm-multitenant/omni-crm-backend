from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from app.core.config import get_settings


TokenPurpose = Literal["access", "mfa_challenge", "tenant_selection"]
ALLOWED_PURPOSES: frozenset[str] = frozenset({"access", "mfa_challenge", "tenant_selection"})
ISSUER = "omni-backend"
AUDIENCE = "omni-api"


class InvalidToken(ValueError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    subject: UUID
    purpose: TokenPurpose
    expires_at: int
    jwt_id: UUID
    session_id: UUID | None = None
    tenant_id: UUID | None = None
    membership_id: UUID | None = None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(
    *,
    user_id: UUID,
    purpose: TokenPurpose,
    ttl_seconds: int,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "purpose": purpose,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid4()),
    }
    for key, value in {
        "sid": session_id,
        "tenant_id": tenant_id,
        "membership_id": membership_id,
    }.items():
        if value is not None:
            payload[key] = str(value)
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(get_settings().jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64encode(signature)}"


def decode_token(token: str, *, expected_purpose: TokenPurpose | None = None) -> TokenClaims:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        if any(
            _b64encode(_b64decode(segment)) != segment
            for segment in (encoded_header, encoded_payload, encoded_signature)
        ):
            raise InvalidToken("non-canonical encoding")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            get_settings().jwt_secret.encode(), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(encoded_signature)):
            raise InvalidToken("invalid signature")
        header = json.loads(_b64decode(encoded_header))
        payload = json.loads(_b64decode(encoded_payload))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise InvalidToken("invalid header")
        purpose = payload["purpose"]
        if purpose not in ALLOWED_PURPOSES or (expected_purpose and purpose != expected_purpose):
            raise InvalidToken("invalid purpose")
        if payload["iss"] != ISSUER or payload["aud"] != AUDIENCE:
            raise InvalidToken("invalid issuer or audience")
        expires_at = int(payload["exp"])
        if expires_at <= int(time.time()):
            raise InvalidToken("expired")
        return TokenClaims(
            subject=UUID(payload["sub"]),
            purpose=purpose,
            expires_at=expires_at,
            jwt_id=UUID(payload["jti"]),
            session_id=UUID(payload["sid"]) if payload.get("sid") else None,
            tenant_id=UUID(payload["tenant_id"]) if payload.get("tenant_id") else None,
            membership_id=UUID(payload["membership_id"]) if payload.get("membership_id") else None,
        )
    except InvalidToken:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidToken("malformed token") from exc
