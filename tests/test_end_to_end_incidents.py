"""Exercise the public simulation workflow from injection to report."""

import json

import pytest

from src.services.simulation_engine import simulation_engine
from src.services.ollama_adapter import ollama_adapter


@pytest.mark.parametrize("service,fault,magnitude", [
    ("payment-service", "SERVICE_CRASH", 1),
    ("payment-service", "LATENCY", 2000),
    ("inventory-service", "RESOURCE_SATURATION", 200),
])
def test_injection_to_postmortem(client, headers, monkeypatch, service, fault, magnitude):
    async def offline(*args, **kwargs):
        return {"content": None, "is_local_llm": False}

    monkeypatch.setattr(ollama_adapter, "generate_response", offline)
    injection = client.post("/api/v1/chaos/inject", headers=headers("lead"), json={
        "service_name": service, "fault_type": fault, "magnitude": magnitude, "duration_sec": 90,
    })
    assert injection.status_code == 201, injection.text
    for _ in range(10):
        simulation_engine.simulate_cycle()

    candidate = client.get("/api/v1/telemetry/incident-candidate")
    assert candidate.status_code == 200, candidate.text
    incident = candidate.json()
    assert incident and incident["root_cause_service"] == service
    incident_id = incident["incident_id"]

    stream = client.get(f"/api/v1/ai/stream-investigation/{incident_id}")
    assert stream.status_code == 200, stream.text
    events = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "WORKFLOW_CHECKPOINT"
    assert events[-1]["state"]["confidence_score"] > 0
    plan_id = events[-1]["state"]["proposed_remediation"]["plan_id"]

    approval = client.post(f"/api/v1/remediation/plans/{plan_id}/approve",
                           headers=headers("lead"), json={"reason": "Reviewed simulated evidence and target"})
    assert approval.status_code == 200, approval.text
    assert approval.json()["state"] == "VERIFIED_SUCCESSFUL"

    report = client.get(f"/api/v1/incidents/{incident_id}/postmortem")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["mode"] == "simulation"
    assert body["agent_trace"] and body["evidence"]
    assert body["remediation_plans"][0]["approved_by"] == "lead"
    assert body["recovery_verification"]
