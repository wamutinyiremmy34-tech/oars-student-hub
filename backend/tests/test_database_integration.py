from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_ready_succeeds_against_real_postgres(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["data"]["checks"]["database"] == "ok"


def test_alembic_upgrade_head_and_check_pass() -> None:
    config = Config(str(ALEMBIC_INI))
    command.upgrade(config, "head")
    command.check(config)  # fails if models and migrations diverge
