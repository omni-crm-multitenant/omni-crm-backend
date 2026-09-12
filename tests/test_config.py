import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_local_settings_allow_fake_external_services() -> None:
    settings = Settings(app_env="local", jwt_secret="local-change-me", billing_mode="mock", _env_file=None)
    assert settings.meta_app_id is None
    assert settings.billing_mode == "mock"


def test_production_rejects_mock_billing() -> None:
    with pytest.raises(ValidationError, match="BILLING_MODE=mock"):
        Settings(app_env="production", jwt_secret="production-secret-value", billing_mode="mock", _env_file=None)


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="non-placeholder JWT_SECRET"):
        Settings(app_env="production", jwt_secret="local-change-me", billing_mode="live", _env_file=None)


def test_smtp_credentials_must_be_complete() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(smtp_username="user", smtp_password=None, _env_file=None)
