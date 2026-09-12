from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PLACEHOLDER_SECRETS = {"", "change-me", "local-change-me", "todo_fill_manually"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "production"] = "local"
    app_name: str = "Omni CRM API"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://omni:omni@localhost:5432/omni"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(default="local-change-me", min_length=8)
    mfa_encryption_key: str = Field(
        default="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        min_length=44,
    )
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    challenge_token_ttl_seconds: int = Field(default=300, ge=60, le=1800)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    billing_mode: Literal["mock", "live"] = "mock"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_tls_mode: Literal["none", "starttls", "tls"] = "none"
    mail_from: str = "no-reply@omni.local"
    auth_public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    app_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")

    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_graph_api_version: str = "v23.0"
    meta_oauth_redirect_uri: AnyHttpUrl | None = None
    meta_webhook_verify_token: str | None = None
    campaign_sync_interval_seconds: int = Field(default=900, ge=60, le=86400)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    @model_validator(mode="after")
    def reject_unsafe_production(self) -> "Settings":
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if self.app_env != "production":
            return self
        if self.jwt_secret.strip().lower() in PLACEHOLDER_SECRETS:
            raise ValueError("Production requires a non-placeholder JWT_SECRET")
        if self.billing_mode == "mock":
            raise ValueError("Production cannot activate paid billing with BILLING_MODE=mock")
        if self.mfa_encryption_key == "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=":
            raise ValueError("Production requires a unique MFA_ENCRYPTION_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
