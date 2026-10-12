"""Each test starts with an isolated database and explicitly provisioned users."""
import os
from pathlib import Path
from dotenv import dotenv_values
import pytest

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

_root = Path(__file__).resolve().parent.parent
_test_url = os.environ.get("TEST_DATABASE_URL", dotenv_values(_root / ".env").get("TEST_DATABASE_URL"))
_test_url_error = "TEST_DATABASE_URL must point to a dedicated PostgreSQL database ending in _test."
if not _test_url:
    raise RuntimeError(_test_url_error)
try:
    _parsed = make_url(_test_url)
except (ArgumentError, ValueError, TypeError):
    raise RuntimeError(_test_url_error) from None
if _parsed.drivername not in {"postgres", "postgresql", "postgresql+psycopg"} or not _parsed.database or not _parsed.database.endswith("_test"):
    raise RuntimeError(_test_url_error)
os.environ["DATABASE_URL"] = _test_url
os.environ["ENVIRONMENT"] = "test"
os.environ["SIMULATION_ENABLED"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""

@pytest.fixture(autouse=True)
def isolated_platform():
    from src.database import Base, engine, init_db
    from src.models.auth import UserRole
    from src.services.auth_service import auth_service
    from src.services.audit_service import audit_service
    from src.services.platform_service import platform_service
    from src.services.chaos_controller import chaos_controller
    from src.services.telemetry_stream import telemetry_stream
    from src.services.event_correlator import event_correlator
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    init_db()
    audit_service.initialize()
    for name, role in [("admin", UserRole.ADMIN), ("lead", UserRole.SRE_LEAD), ("operator", UserRole.OPERATOR), ("viewer", UserRole.VIEWER)]:
        auth_service.provision_user(name, f"test-{name}-credential-2026", role)
    platform_service.initialize()
    chaos_controller.clear_all_faults()
    for service in telemetry_stream._history:
        telemetry_stream.flush_service_history(service)
    telemetry_stream._last_heartbeat.clear()
    event_correlator._recent_alerts.clear()
    event_correlator._active_groups.clear()
    yield
    chaos_controller.clear_all_faults()

@pytest.fixture
def headers():
    from src.services.auth_service import auth_service
    return lambda name: {"Authorization": "Bearer " + auth_service.create_access_token(auth_service.get_user_by_username(name)).access_token}

@pytest.fixture
def client(headers):
    from fastapi.testclient import TestClient
    from src.main import app
    result = TestClient(app, headers=headers("operator"))
    yield result
    result.close()


def pytest_sessionfinish(session, exitstatus):
    from src.database import Base, engine
    Base.metadata.drop_all(engine)
    engine.dispose()
