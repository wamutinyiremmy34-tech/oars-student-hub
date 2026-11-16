import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

# Test-only values. Set before the app is imported. CI and developers may override via the environment.
os.environ["APP_ENV"] = "testing"
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://oars:oars_dev_password@localhost:5432/oars_test"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-real-use-0123456789")
os.environ["LOG_FORMAT"] = "console"
# Most tests make many auth calls from one fake IP; the rate-limit tests lower this explicitly.
os.environ["AUTH_RATE_LIMIT_ATTEMPTS"] = "1000"
os.environ.setdefault("STORAGE_LOCAL_PATH", tempfile.mkdtemp(prefix="oars-test-storage-"))

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app() -> FastAPI:
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- database fixtures


@pytest.fixture(scope="session")
def migrated_engine() -> Engine:
    """The test database, migrated to head with the real Alembic migrations (not create_all)."""
    from alembic.config import Config

    from alembic import command
    from app.db.session import get_engine

    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    return get_engine()


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    """One transaction per test, rolled back afterwards.

    Services call session.commit(); with join_transaction_mode="create_savepoint" that only
    releases a SAVEPOINT, so nothing is ever really committed and tests stay isolated.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def email_outbox():  # type: ignore[no-untyped-def]
    from helpers import MemoryEmailSender

    return MemoryEmailSender()


@pytest.fixture
def storage(tmp_path: Path):  # type: ignore[no-untyped-def]
    from app.providers.storage.local import LocalStorage

    return LocalStorage(tmp_path / "files")


@pytest.fixture
def api_client(app: FastAPI, db: Session, email_outbox, storage) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    """HTTP client bound to the per-test transaction, with captured email and isolated file storage."""
    from helpers import override_db

    override_db(app, db)
    app.state.email_sender = email_outbox
    app.state.storage = storage
    with TestClient(app) as test_client:
        yield test_client
