import uuid

import pytest
from pydantic import ValidationError

from app.modules.audit.service import scrub
from app.modules.auth.schemas import LoginIn, RegisterIn, ResetPasswordIn


def test_scrub_redacts_sensitive_keys_recursively() -> None:
    cleaned = scrub(
        {
            "reason": "spam",
            "password": "hunter2",
            "nested": {"refresh_token": "abc", "Authorization": "Bearer x", "ok": 1},
            "items": [{"secret_key": "s"}, {"name": "n"}],
        }
    )
    assert cleaned["reason"] == "spam"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"] == {
        "refresh_token": "[REDACTED]",
        "Authorization": "[REDACTED]",
        "ok": 1,
    }
    assert cleaned["items"] == [{"secret_key": "[REDACTED]"}, {"name": "n"}]


def _register(**overrides: object) -> RegisterIn:
    data: dict[str, object] = {
        "email": "Amina@Example.com",
        "password": "correct-horse-battery",
        "full_name": "  Amina Nakato ",
        "institution_id": uuid.uuid4(),
    }
    return RegisterIn(**{**data, **overrides})  # type: ignore[arg-type]


def test_register_schema_accepts_valid_input_and_trims_name() -> None:
    assert _register().full_name == "Amina Nakato"
    assert _register(phone="+256700123456").phone == "+256700123456"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"email": "not-an-email"},
        {"phone": "12ab"},
        {"full_name": "   "},
        {"institution_id": "not-a-uuid"},
    ],
)
def test_register_schema_rejects_invalid_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _register(**overrides)


def test_login_and_reset_schemas_bound_input_size() -> None:
    with pytest.raises(ValidationError):
        LoginIn(email="a@example.com", password="x" * 129)
    with pytest.raises(ValidationError):
        ResetPasswordIn(token="t" * 30, new_password="short")
    with pytest.raises(ValidationError):
        ResetPasswordIn(token="short", new_password="long-enough-password")
