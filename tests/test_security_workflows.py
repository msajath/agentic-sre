"""Regressions for approval bypass, API contracts, durable writes and startup."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from src.main import app
from src.database import Base, engine, SessionLocal, UserModel, AuditLogModel
from src.models.auth import UserRole
from src.models.audit import AuditEventType
from src.models.chaos import ChaosInjectionRequest, FaultType
from src.models.incident import IncidentState
from src.models.remediation import RemediationActionType, RemediationState
from src.services.auth_service import auth_service
from src.services.audit_service import audit_service, AuditService
from src.services.incident_service import incident_service
from src.services.remediation_engine import remediation_engine
from src.services.chaos_controller import chaos_controller
from src.services.simulation_engine import simulation_engine
from src.services.telemetry_stream import telemetry_stream
from src.services.anomaly_detector import anomaly_detector
from src.services.platform_service import platform_service
from src.services.ollama_adapter import ollama_adapter

def incident_and_plan():
    incident = incident_service.create_incident("Regression incident", "Isolated review fixture", root_cause_service="payment-service", affected_services=["payment-service", "order-service"])
    plan = remediation_engine.propose_plan(incident.incident_id, "payment-service", RemediationActionType.RESTART_SERVICE)
    return incident, plan

@pytest.mark.parametrize("path,method,payload", [
    ("/api/v1/chaos/inject", "post", {"service_name":"payment-service", "fault_type":"SERVICE_CRASH"}),
    ("/api/v1/chaos/reset", "post", None),
    ("/api/v1/settings", "post", {"error_rate_threshold":0.1, "latency_p95_threshold_ms":1000}),
    ("/api/v1/knowledge/documents", "post", {"title":"Test book", "target_services":["payment-service"], "content":"A real runbook content"}),
    ("/api/v1/telemetry/events", "post", {"service_name":"payment-service"}),
    ("/api/v1/incidents", "get", None),
    ("/api/v1/audit/logs", "get", None),
    ("/api/v1/audit/legacy", "get", None),
])
def test_authentication_required(path, method, payload):
    client = TestClient(app)
    assert client.request(method, path, json=payload).status_code == 401

@pytest.mark.parametrize("name", ["viewer", "operator"])
def test_chaos_requires_lead(client, headers, name):
    response = client.post("/api/v1/chaos/inject", headers=headers(name), json={"service_name":"payment-service", "fault_type":"SERVICE_CRASH"})
    assert response.status_code == 403
    assert not chaos_controller.get_active_faults()

def test_chaos_actor_cannot_be_spoofed(client, headers):
    response = client.post("/api/v1/chaos/inject", headers=headers("lead"), json={"service_name":"payment-service", "fault_type":"LATENCY", "magnitude":1500, "injected_by":"admin"})
    assert response.status_code == 201
    assert response.json()["injected_by"] == "lead"
    assert audit_service.get_entries()[0].actor == "lead"

def test_pending_verification_cannot_resolve_incident(client, headers):
    incident, plan = incident_and_plan()
    simulation_engine.simulate_cycle()
    assert TestClient(app).post(f"/api/v1/remediation/plans/{plan.plan_id}/verify").status_code == 401
    assert client.post(f"/api/v1/remediation/plans/{plan.plan_id}/verify", headers=headers("viewer")).status_code == 403
    assert client.post(f"/api/v1/remediation/plans/{plan.plan_id}/verify", headers=headers("lead")).status_code == 409
    assert remediation_engine.get_plan(plan.plan_id).state == RemediationState.PENDING_APPROVAL
    assert incident_service.get_incident(incident.incident_id).state == IncidentState.DETECTED

def test_full_http_approval_flow(client, headers):
    incident, plan = incident_and_plan()
    chaos_controller.inject_fault(ChaosInjectionRequest(service_name="payment-service", fault_type=FaultType.SERVICE_CRASH))
    assert client.post(f"/api/v1/remediation/plans/{plan.plan_id}/approve", headers=headers("viewer"), json={"reason":"Reviewed"}).status_code == 403
    response = client.post(f"/api/v1/remediation/plans/{plan.plan_id}/approve", headers=headers("lead"), json={"reason":"Reviewed root cause and impact"})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "VERIFIED_SUCCESSFUL"
    assert incident_service.get_incident(incident.incident_id).state == IncidentState.RESOLVED
    assert audit_service.verify_integrity().is_valid

def test_auto_propose_without_anomalies(client):
    incident, plan = incident_and_plan()
    response = client.post(f"/api/v1/remediation/auto-propose/{incident.incident_id}")
    assert response.status_code == 201, response.text
    assert response.json()["plan_id"] == plan.plan_id

@pytest.mark.parametrize("kind", ["LATENCY", "RESOURCE_SATURATION"])
def test_frontend_fault_types_are_valid(client, headers, kind):
    assert client.post("/api/v1/chaos/inject", headers=headers("lead"), json={"service_name":"payment-service", "fault_type":kind}).status_code == 201

def test_unknown_incident_is_404(client):
    assert client.post("/api/v1/ai/analyze-incident/INC-NOTFOUND").status_code == 404
    assert client.get("/api/v1/ai/stream-investigation/INC-NOTFOUND").status_code == 404

def test_detection_has_stable_persisted_identity():
    chaos_controller.inject_fault(ChaosInjectionRequest(service_name="payment-service", fault_type=FaultType.SERVICE_CRASH))
    simulation_engine.simulate_cycle()
    first = anomaly_detector.identify_potential_incident()
    second = anomaly_detector.identify_potential_incident()
    assert first.incident_id == second.incident_id
    assert incident_service.get_incident(first.incident_id)
    assert len(incident_service.list_incidents()) == 1

def test_database_failure_does_not_publish_incident(client, monkeypatch):
    def fail(*args, **kwargs):
        raise OperationalError("commit", {}, Exception("unavailable"))
    monkeypatch.setattr(audit_service, "record_event", fail)
    response = client.post("/api/v1/incidents", params={"title":"Storage failure", "description":"Should rollback state"})
    assert response.status_code == 503
    assert not incident_service.list_incidents()

def test_audit_failure_does_not_publish_plan(monkeypatch):
    incident = incident_service.create_incident("Storage test", "Rollback plan proposal", root_cause_service="payment-service")
    def fail(*args, **kwargs):
        raise OperationalError("commit", {}, Exception("unavailable"))
    monkeypatch.setattr(audit_service, "record_event", fail)
    with pytest.raises(OperationalError):
        remediation_engine.propose_plan(incident.incident_id, "payment-service", RemediationActionType.RESTART_SERVICE)
    assert not remediation_engine.list_plans()

def test_genesis_payload_tampering_is_detected():
    ledger = AuditService(persist_db=False)
    ledger._ledger[0].action_summary = "tampered"
    assert not ledger.verify_integrity().is_valid

def test_persisted_audit_tampering_is_detected():
    with SessionLocal.begin() as session:
        session.get(AuditLogModel, "GENESIS-BLOCK").action_summary = "tampered"
    assert not audit_service.verify_integrity().is_valid
    with pytest.raises(RuntimeError):
        audit_service.initialize()

def test_concurrent_audit_writes_have_one_chain():
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda number: audit_service.record_event(AuditEventType.INCIDENT_NOTE, "test", "SYSTEM", "test", f"Concurrent event {number}"), range(12)))
    assert audit_service.verify_integrity().is_valid
    assert len(audit_service.get_entries()) == 12

def test_account_deactivation_revokes_existing_token(client, headers):
    token = headers("lead")
    with SessionLocal.begin() as session:
        session.get(UserModel, "lead").is_active = False
    assert client.get("/api/v1/incidents", headers=token).status_code == 401

def test_fresh_boot_initializes_before_seeding(monkeypatch):
    from src.config import settings
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)  # Startup expects migrations to have run first.
    monkeypatch.setattr(settings, "bootstrap_admin_password", "fresh-boot-long-password")
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"username":"admin", "password":"fresh-boot-long-password"})
        assert response.status_code == 200, response.text
        assert client.get("/readyz").status_code == 200
    assert not simulation_engine.is_running

def test_legacy_demo_credentials_are_disabled():
    auth_service.provision_user("admin", "AdminSre@2026", UserRole.ADMIN)
    auth_service.initialize()
    assert auth_service.authenticate_user("admin", "AdminSre@2026") is None

def test_runbook_persists_and_search_quotes_real_content(client, headers):
    content = "Inspect the zephyr connector queue before restarting any workers."
    response = client.post("/api/v1/knowledge/documents", headers=headers("operator"), json={"title":"Zephyr queue", "target_services":["payment-service"], "content":content})
    assert response.status_code == 201
    platform_service.initialize()
    result = client.get("/api/v1/knowledge/search", params={"query":"zephyr"}).json()
    assert result["citations"][0]["excerpt"] == content
    assert client.get("/api/v1/knowledge/search", params={"query":"impossiblexyz"}).json()["citations"] == []

def test_settings_updates_are_effective_and_persisted(client, headers):
    from src.config import settings
    old_error, old_latency = settings.anomaly_error_rate_threshold, settings.anomaly_latency_p95_ms
    try:
        assert client.post("/api/v1/settings", json={"error_rate_threshold":0.1,"latency_p95_threshold_ms":1200}).status_code == 403
        assert client.post("/api/v1/settings", headers=headers("admin"), json={"error_rate_threshold":0.1,"latency_p95_threshold_ms":1200}).status_code == 200
        assert settings.anomaly_error_rate_threshold == 0.1
        settings.anomaly_error_rate_threshold = old_error
        platform_service.initialize()
        assert settings.anomaly_error_rate_threshold == 0.1
    finally:
        settings.anomaly_error_rate_threshold, settings.anomaly_latency_p95_ms = old_error, old_latency

@pytest.mark.parametrize("scenario", ["SCN-01", "SCN-02", "SCN-03", "SCN-04", "SCN-05"])
def test_benchmarks_measure_actual_isolated_runs(client, scenario):
    response = client.post(f"/api/v1/evaluations/replay/{scenario}")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PASSED", response.text
    assert not chaos_controller.get_active_faults()
    assert not incident_service.list_incidents()
    metrics = client.get("/api/v1/evaluations/benchmarks").json()["metrics"]
    assert metrics["total_benchmark_runs"] == 1
    assert metrics["unsafe_action_rate"] is None

def test_stream_persists_human_checkpoint(client, monkeypatch):
    incident, plan = incident_and_plan()
    async def offline(*args, **kwargs):
        return {"content":None,"is_local_llm":False}
    monkeypatch.setattr(ollama_adapter, "generate_response", offline)
    response = client.get(f"/api/v1/ai/stream-investigation/{incident.incident_id}")
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "WORKFLOW_CHECKPOINT"
    assert events[-1]["state"]["proposed_remediation"]["plan_id"] == plan.plan_id
    assert remediation_engine.get_plan(plan.plan_id).state == RemediationState.PENDING_APPROVAL


def test_viewer_cannot_start_approval_workflow(client, headers):
    incident = incident_service.create_incident("Viewer regression", "No proposal allowed", root_cause_service="payment-service")
    response = client.get(f"/api/v1/ai/stream-investigation/{incident.incident_id}", headers=headers("viewer"))
    assert response.status_code == 403
    assert not remediation_engine.list_plans()


@pytest.mark.parametrize("condition,expected_status", [("no_root", 400), ("unknown_service", 400), ("closed", 409), ("telemetry_only", 409)])
def test_stream_rejects_invalid_workflow_before_sending_events(client, monkeypatch, condition, expected_status):
    from src.config import settings
    root = None if condition == "no_root" else "unknown-service" if condition == "unknown_service" else "payment-service"
    incident = incident_service.create_incident("Invalid workflow", "Validate before streaming", root_cause_service=root)
    if condition == "closed":
        incident_service.transition_state(incident.incident_id, IncidentState.CLOSED, "Closed by review", "lead", "SRE_LEAD")
    elif condition == "telemetry_only":
        monkeypatch.setattr(settings, "simulation_enabled", False)
    response = client.get(f"/api/v1/ai/stream-investigation/{incident.incident_id}")
    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"
    assert not remediation_engine.list_plans()


@pytest.mark.parametrize("condition", ["closed", "telemetry_only", "unknown_service"])
def test_auto_propose_rejects_invalid_plan_with_client_error(client, monkeypatch, condition):
    from src.config import settings
    incident = incident_service.create_incident("Invalid proposal", "Reject invalid remediation", root_cause_service="unknown-service" if condition == "unknown_service" else "payment-service")
    if condition == "closed":
        incident_service.transition_state(incident.incident_id, IncidentState.CLOSED, "Closed by review", "lead", "SRE_LEAD")
    elif condition == "telemetry_only":
        monkeypatch.setattr(settings, "simulation_enabled", False)
    response = client.post(f"/api/v1/remediation/auto-propose/{incident.incident_id}")
    assert response.status_code == 400
    assert not remediation_engine.list_plans()

def test_websocket_requires_authentication(headers):
    with TestClient(app) as client:
        with client.websocket_connect("/ws/dashboard") as socket:
            socket.send_json({"access_token":"invalid"})
            assert socket.receive()["code"] == 1008
        with client.websocket_connect("/ws/dashboard") as socket:
            socket.send_json({"access_token":headers("viewer")["Authorization"].split(" ")[1]})
            assert socket.receive_json()["type"] == "TELEMETRY_SNAPSHOT"

def test_lower_level_restart_cannot_bypass_approval():
    from src.services.tool_gateway import tool_gateway
    _, plan = incident_and_plan()
    with pytest.raises(PermissionError):
        tool_gateway.restart_pod("payment-service", plan.plan_id)


def test_verification_checks_fresh_samples_and_affected_callers():
    incident, plan = incident_and_plan()
    remediation_engine.approve_and_execute(plan.plan_id, "lead", "SRE_LEAD", "Review complete")
    chaos_controller.inject_fault(ChaosInjectionRequest(service_name="order-service", fault_type=FaultType.LATENCY, magnitude=2500))
    for _ in range(5):
        simulation_engine.simulate_cycle()
    assert remediation_engine.verify_recovery(plan.plan_id) is False
    assert remediation_engine.get_plan(plan.plan_id).state == RemediationState.FAILED_VERIFICATION
    chaos_controller.clear_all_faults()
    telemetry_stream.flush_service_history("payment-service")
    assert remediation_engine.verify_recovery(plan.plan_id) is False


def test_audit_initialization_restores_only_known_missing_genesis():
    audit_service.record_event(AuditEventType.INCIDENT_NOTE, "test", "SYSTEM", "test", "Prior first-boot entry")
    with SessionLocal.begin() as session:
        session.delete(session.get(AuditLogModel, "GENESIS-BLOCK"))
    audit_service.initialize()
    assert audit_service.verify_integrity().is_valid


def test_execution_failure_does_not_claim_rollback(monkeypatch):
    incident, plan = incident_and_plan()
    def fail(plan):
        raise RuntimeError("simulated action failed")
    monkeypatch.setattr(remediation_engine, "_execute_action", fail)
    with pytest.raises(RuntimeError):
        remediation_engine.approve_and_execute(plan.plan_id, "lead", "SRE_LEAD", "Reviewed")
    assert remediation_engine.get_plan(plan.plan_id).state == RemediationState.EXECUTION_FAILED
    assert incident_service.get_incident(incident.incident_id).state != IncidentState.RESOLVED


def test_environment_settings_are_validated(monkeypatch):
    from src.config import Settings
    monkeypatch.setenv("SRE_DEBUG", "true")
    monkeypatch.setenv("DEBUG", "release")
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://sre.example.com"]')
    configured = Settings.from_env()
    assert configured.debug is True
    assert configured.port == 8123
    assert configured.allowed_origins == ["https://sre.example.com"]
    with pytest.raises(ValueError):
        Settings(environment="production")
    with pytest.raises(ValueError):
        Settings(secret_key="short")
    with pytest.raises(ValueError):
        Settings(allowed_origins=["*"])
