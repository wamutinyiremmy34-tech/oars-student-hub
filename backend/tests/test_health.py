from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db


class _HealthySession:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None


class _BrokenSession:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused: secret-host"))


def _override(app: FastAPI, session: object) -> None:
    def fake_db() -> Iterator[object]:
        yield session

    app.dependency_overrides[get_db] = fake_db


def test_health_is_available_on_both_paths(client: TestClient) -> None:
    for path in ("/health", "/api/v1/health"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ok"
        assert body["meta"] == {}


def test_ready_ok_when_database_responds(app: FastAPI) -> None:
    _override(app, _HealthySession())
    response = TestClient(app).get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ready", "checks": {"database": "ok"}}


def test_ready_returns_503_without_leaking_details(app: FastAPI) -> None:
    _override(app, _BrokenSession())
    for path in ("/ready", "/api/v1/ready"):
        response = TestClient(app).get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_ready"
        assert "secret-host" not in response.text
