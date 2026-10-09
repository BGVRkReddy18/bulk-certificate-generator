"""
Shared pytest fixtures for the AEREO test suite.

* Uses a separate in-memory SQLite database for every test session.
* Redirects certificate storage to a temporary directory.
* Provides a deterministic ``client`` that processes jobs synchronously
  (via monkey-patching ``start_job_processing``).
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Override settings BEFORE importing app modules so the config picks them up.
# ---------------------------------------------------------------------------

# We set env vars before importing app.config so that ``Settings`` reads them.
_tmp_storage = tempfile.mkdtemp(prefix="aereo_test_certs_")
os.environ["DATABASE_URL"] = "sqlite:///file::memory:?cache=shared&uri=true"
os.environ["STORAGE_DIR"] = _tmp_storage

from app.config import settings  # noqa: E402  (must come after env override)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.job_service import process_job_sync  # noqa: E402


# ---------------------------------------------------------------------------
# Engine / session bound to an in-memory DB
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite:///file::memory:?cache=shared&uri=true",
    connect_args={"check_same_thread": False},
)
_TestingSession = sessionmaker(bind=_test_engine, autocommit=False, autoflush=False)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create all tables once for the test session."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table between tests for isolation."""
    yield
    with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def db():
    """Provide a raw DB session for direct inspection in tests."""
    session = _TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    """
    FastAPI TestClient that **synchronously** processes jobs.

    ``start_job_processing`` is monkey-patched to call
    ``process_job_sync`` so that by the time the POST returns, all
    recipients have been processed and tests can assert deterministically.
    """

    def _sync_start(job_id: str) -> None:
        # Must import a fresh session factory that points at the test DB
        from app.services import job_service

        original_session_local = job_service.SessionLocal
        job_service.SessionLocal = _TestingSession
        try:
            process_job_sync(job_id)
        finally:
            job_service.SessionLocal = original_session_local

    with patch("app.routers.jobs.start_job_processing", side_effect=_sync_start):
        with TestClient(app, raise_server_exceptions=False) as tc:
            yield tc


@pytest.fixture()
def storage_dir() -> Path:
    """Return the temporary storage directory used by tests."""
    return Path(_tmp_storage)
