import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError


def test_unknown_route_returns_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["x-request-id"]


def test_app_error_maps_to_status_and_code(app: FastAPI) -> None:
    @app.get("/__conflict")
    def conflict() -> None:
        raise ConflictError("Already exists.", code="duplicate_email")

    @app.get("/__forbidden")
    def forbidden() -> None:
        raise ForbiddenError()

    client = TestClient(app)
    r1 = client.get("/__conflict")
    assert r1.status_code == 409
    assert r1.json()["error"]["code"] == "duplicate_email"
    r2 = client.get("/__forbidden")
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "forbidden"


def test_validation_error_lists_fields_without_echoing_input(app: FastAPI) -> None:
    @app.get("/__num")
    def num(n: int) -> dict[str, int]:
        return {"n": n}

    response = TestClient(app).get("/__num", params={"n": "super-secret-value"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "query.n"
    assert "super-secret-value" not in response.text


def test_unhandled_exception_is_hidden_and_still_has_headers(app: FastAPI) -> None:
    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("internal detail: db password is hunter2")

    response = TestClient(app).get("/__boom")
    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_valid_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-abcdef123456"})
    assert response.headers["x-request-id"] == "trace-abcdef123456"


def test_invalid_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert response.headers["x-request-id"] != "bad id with spaces!"
    assert len(response.headers["x-request-id"]) == 32


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"

    denied = client.options(
        "/api/v1/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_production_app_enables_hsts_and_disables_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.oars.example")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "oars-files")
    get_settings.cache_clear()

    from app.main import create_app

    client = TestClient(create_app())
    assert "strict-transport-security" in client.get("/health").headers
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
