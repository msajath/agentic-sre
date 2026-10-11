"""PostgreSQL configuration, startup, archived history, and transaction regressions."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.database import Base, PlatformRecordModel, SessionLocal, engine, parse_database_url
from src.models.audit import AuditEventType
from src.services.audit_service import audit_service
from src.services.incident_service import incident_service


@pytest.mark.parametrize("value", [None, "", "  ", "invalid-url", "mysql://localhost/test", "postgresql://localhost/"])
def test_database_configuration_rejects_missing_or_non_postgres_urls(value):
    with pytest.raises(ValueError, match="DATABASE_URL"):
        parse_database_url(value)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_database_configuration_normalizes_postgres_driver(scheme):
    url = parse_database_url(f"{scheme}://sre:example@localhost:55432/agentic_sre_test")
    assert url.drivername == "postgresql+psycopg"
    assert url.database == "agentic_sre_test"
    assert url.host == "localhost"
    assert url.port == 55432


def test_postgres_requires_migration_before_startup():
    from src.database import init_db
    Base.metadata.drop_all(engine)
    with pytest.raises(RuntimeError, match="db:migrate"):
        init_db()
    Base.metadata.create_all(engine)


def test_legacy_history_is_reported_as_unverified_archive(client):
    original = {
        "log_id": "LEGACY-ENTRY",
        "prev_hash": "0" * 64,
        "entry_hash": "1" * 64,
        "action_summary": "Unverified historical action",
    }
    archived = {"verified": False, "source": "legacy audit ledger", "record": original}
    summary = {"verified": False, "archived_records": 1, "reason": "Historical chain could not be verified"}
    with SessionLocal.begin() as session:
        session.add(PlatformRecordModel(key="legacy-audit:LEGACY-ENTRY", payload=json.dumps(archived)))
        session.add(PlatformRecordModel(key="migration:postgres-audit-archive", payload=json.dumps(summary)))

    response = client.get("/api/v1/audit/legacy")
    assert response.status_code == 200
    assert response.json() == {"verified": False, "summary": summary, "records": [archived]}
    assert audit_service.verify_integrity().is_valid
    assert original["log_id"] not in {entry.log_id for entry in audit_service.get_entries()}


def test_legacy_archive_limit_is_enforced(client):
    with SessionLocal.begin() as session:
        for index in range(3):
            session.add(PlatformRecordModel(
                key=f"legacy-audit:ENTRY-{index}",
                payload=json.dumps({"verified": False, "record": {"log_id": f"ENTRY-{index}"}}),
            ))
    response = client.get("/api/v1/audit/legacy", params={"limit": 2})
    assert response.status_code == 200
    assert [entry["record"]["log_id"] for entry in response.json()["records"]] == ["ENTRY-0", "ENTRY-1"]
    assert client.get("/api/v1/audit/legacy", params={"limit": 201}).status_code == 422


def test_concurrent_state_transactions_append_one_audit_chain():
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda number: incident_service.create_incident(
            f"Concurrent incident {number}", "Transactional PostgreSQL audit chain", root_cause_service="payment-service"
        ), range(12)))
    audit_service.record_event(AuditEventType.INCIDENT_NOTE, "test", "SYSTEM", "test", "Concurrent state writes complete")
    assert len(incident_service.list_incidents()) == 12
    assert audit_service.verify_integrity().is_valid
