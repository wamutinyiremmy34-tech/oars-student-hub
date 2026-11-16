"""Application settings. All configuration comes from environment variables (or the repo-root .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,  # never echo secret values in validation errors
    )

    app_name: str = "OARS Student Solutions API"
    app_env: Literal["development", "testing", "production"] = "development"
    api_v1_prefix: str = "/api/v1"

    # Database (psycopg v3 driver)
    database_url: str
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)

    # Auth
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "oars-student-solutions"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    jwt_audience: str = "oars-api"
    refresh_cookie_name: str = "oars_refresh"
    cookie_domain: str | None = None
    cookie_samesite: Literal["lax", "strict"] = "lax"
    email_verification_ttl_hours: int = Field(default=24, ge=1, le=168)
    password_reset_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    # Base URL of the web app, used to build links in emails.
    public_app_url: str = "http://localhost:5173"

    # Rate limiting (in-process, per API instance)
    rate_limit_enabled: bool = True
    auth_rate_limit_attempts: int = Field(default=10, ge=1, le=100000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    # Number of reverse proxies in front of the API that append to X-Forwarded-For (0 = none).
    trusted_proxy_count: int = Field(default=0, ge=0, le=5)

    # File storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = str(REPO_ROOT / "storage")
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # set for MinIO or other S3-compatible stores
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    download_url_ttl_seconds: int = Field(default=60, ge=10, le=900)
    malware_scanner: Literal["none"] = "none"

    # Payments. Only the development FakeProvider exists; a real provider is a later decision.
    payment_provider: Literal["fake"] = "fake"
    payment_pending_minutes: int = Field(default=30, ge=5, le=1440)
    payment_webhook_tolerance_seconds: int = Field(default=300, ge=30, le=3600)

    # Printing
    print_retention_days: int = Field(default=30, ge=1, le=3650)
    print_orphan_upload_hours: int = Field(default=24, ge=1, le=720)
    max_print_pages_per_document: int = Field(default=500, ge=1, le=5000)
    # Pay-on-pickup abuse controls (a shop may override the outstanding-orders limit).
    max_outstanding_pickup_orders: int = Field(default=2, ge=0, le=50)
    max_pickup_order_total_ugx: int = Field(default=100_000, ge=1000, le=50_000_000)
    max_active_orders_per_student: int = Field(default=10, ge=1, le=200)

    # HTTP (comma-separated in the environment)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list exact origins; '*' is not allowed")
        return value

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the 'postgresql+psycopg://' driver")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def _secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def _production_rules(self) -> Self:
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if self.app_env == "production":
            if self.storage_backend == "local":
                raise ValueError(
                    "STORAGE_BACKEND must be 's3' in production (no local disk storage)"
                )
            if "change-me" in self.jwt_secret_key.get_secret_value().lower():
                raise ValueError("JWT_SECRET_KEY must not be a placeholder in production")
            if not self.cors_origins or any(
                not o.startswith("https://") for o in self.cors_origins
            ):
                raise ValueError("CORS_ORIGINS must be non-empty and HTTPS-only in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def payments_available(self) -> bool:
        """Online payments are never available on the development FakeProvider in production."""
        return not (self.is_production and self.payment_provider == "fake")

    @property
    def cookie_secure(self) -> bool:
        return self.is_production

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
