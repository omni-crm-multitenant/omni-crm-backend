from uuid import uuid4

import pytest

from app.core.tokens import InvalidToken, decode_token, issue_token


def test_token_purpose_is_enforced() -> None:
    token = issue_token(user_id=uuid4(), purpose="tenant_selection", ttl_seconds=300)
    assert decode_token(token, expected_purpose="tenant_selection").purpose == "tenant_selection"
    with pytest.raises(InvalidToken):
        decode_token(token, expected_purpose="access")


def test_tampered_token_is_rejected() -> None:
    token = issue_token(user_id=uuid4(), purpose="mfa_challenge", ttl_seconds=300)
    with pytest.raises(InvalidToken):
        decode_token(token[:-1] + ("a" if token[-1] != "a" else "b"))
