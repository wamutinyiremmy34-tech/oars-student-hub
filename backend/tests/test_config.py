import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "database_url": "postgresql+psycopg://u:p@localhost:5432/db",
    "jwt_secret_key": "x" * 40,
}


PROD_STORAGE = {"storage_backend": "s3", "s3_bucket": "oars-files"}


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[arg-type]


def test_valid_development_settings() -> None:
    settings = make(app_env="development")
    assert settings.docs_enabled is True
    assert settings.is_production is False


def test_cors_origins_are_parsed_from_comma_separated_string() -> None:
    settings = make(cors_origins="http://a.test, http://b.test/")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_wildcard_cors_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(cors_origins="*")


def test_short_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(jwt_secret_key="short")


def test_wrong_database_driver_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(database_url="postgresql://u:p@localhost/db")


def test_production_requires_https_origins() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production", cors_origins="http://app.example.com", **PROD_STORAGE)


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError):
        make(
            app_env="production",
            cors_origins="https://app.example.com",
            jwt_secret_key="change-me-" + "a" * 30,
            **PROD_STORAGE,
        )


def test_production_settings_disable_docs() -> None:
    settings = make(app_env="production", cors_origins="https://app.example.com", **PROD_STORAGE)
    assert settings.docs_enabled is False


def test_secret_is_not_revealed_in_repr() -> None:
    assert "x" * 40 not in repr(make())


def test_local_disk_storage_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production", cors_origins="https://app.example.com")


def test_s3_storage_requires_a_bucket() -> None:
    with pytest.raises(ValidationError):
        make(storage_backend="s3")


def test_online_payments_are_unavailable_on_the_fake_provider_in_production() -> None:
    assert make(app_env="development").payments_available is True
    assert make(app_env="testing").payments_available is True
    production = make(app_env="production", cors_origins="https://app.example.com", **PROD_STORAGE)
    assert production.payment_provider == "fake" and production.payments_available is False


def test_print_and_payment_limits_are_bounded() -> None:
    for bad in (
        {"print_retention_days": 0},
        {"max_pickup_order_total_ugx": 5},
        {"payment_pending_minutes": 1},
        {"max_active_orders_per_student": 0},
    ):
        with pytest.raises(ValidationError):
            make(**bad)
