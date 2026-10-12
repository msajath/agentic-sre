"""The four investigation stages report evidence and preserve the human approval gate."""
import asyncio
import json

import httpx

from src.models.incident import IncidentSeverity
from src.services.incident_service import incident_service
from src.services.multi_agent_orchestrator import MultiAgentWorkflowState, multi_agent_orchestrator
from src.services.ollama_adapter import OllamaAdapter, ollama_adapter


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_all_agent_stages_report_bounded_evidence_and_human_gate(client, monkeypatch):
    async def offline(*args, **kwargs):
        return {"content": None, "is_local_llm": False}

    monkeypatch.setattr(ollama_adapter, "generate_response", offline)
    incident = incident_service.create_incident(
        "Payment investigation", "Trace simulated service health", severity=IncidentSeverity.LOW,
        root_cause_service="payment-service",
        affected_services=["order-service", "auth-service", "inventory-service", "notification-service"],
    )
    response = client.get(f"/api/v1/ai/stream-investigation/{incident.incident_id}")
    assert response.status_code == 200
    trace = events(response)
    completed = [event["step"] for event in trace if event["type"] == "NODE_COMPLETE"]
    assert [step["node"] for step in completed] == ["TRIAGE", "INVESTIGATION", "ROOT_CAUSE_ANALYSIS"]
    assert completed[0]["output"]["severity"] == "LOW"
    investigation = completed[1]
    assert len(investigation["output"]["inspected_nodes"]) == 3
    assert len(investigation["output"]["uninspected_nodes"]) == 2
    assert len(investigation["tools_called"]) == 9
    assert any(evidence["source"] == "Registered topology" for evidence in trace[-1]["state"]["evidence_bundle"])
    rca = completed[2]
    assert rca["output"]["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert rca["output"]["confidence"] == 0.0
    checkpoint = trace[-1]
    assert checkpoint["type"] == "WORKFLOW_CHECKPOINT"
    assert checkpoint["step"]["node"] == "REMEDIATION"
    assert checkpoint["state"]["approval_state"] == "PENDING_APPROVAL"
    assert any("fresh evidence" in condition.lower() for condition in checkpoint["step"]["output"]["preconditions"])


def test_root_cause_handles_missing_metrics_without_false_confidence(monkeypatch):
    async def offline(*args, **kwargs):
        return {"content": None, "is_local_llm": False}

    monkeypatch.setattr(ollama_adapter, "generate_response", offline)
    state = MultiAgentWorkflowState(incident_id="INC-NULL", blast_radius=["payment-service"],
                                    root_cause_service="payment-service", evidence_bundle=[
                                        {"source": "Simulated telemetry", "service": "payment-service",
                                         "error_rate": None, "p95_latency_ms": None, "faults": None},
                                    ])
    step = asyncio.run(multi_agent_orchestrator.run_root_cause_node(state))
    assert step.output["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert state.confidence_score == 0.0
    assert state.hypotheses[0]["is_accepted"] is False


def test_ollama_adapter_selects_installed_model_and_requires_nonempty_result(monkeypatch):
    adapter = OllamaAdapter(default_model="llama3.1")

    class Response:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Client:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args):
            return Response({"models": [{"name": "gemma4:latest"}]})

        async def post(self, *args, **kwargs):
            self.calls.append(kwargs["json"])
            return Response({"response": "A concise explanation", "done": True})

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = asyncio.run(adapter.generate_response("Explain an alert"))
    health = asyncio.run(adapter.check_health())
    assert health["is_online"] and health["can_generate"]
    assert health["selected_model"] == "gemma4:latest"
    assert health["has_default_model"] is False
    assert result["is_local_llm"] is True
    assert result["model"] == "gemma4:latest"
    assert Client.calls[-1]["model"] == "gemma4:latest"
    assert Client.calls[-1]["think"] is False
    assert Client.calls[-1]["options"]["num_predict"] == 96

    async def empty_post(self, *args, **kwargs):
        return Response({"response": "", "done": True})

    monkeypatch.setattr(Client, "post", empty_post)
    fallback = asyncio.run(adapter.generate_response("Explain an alert"))
    assert fallback["is_local_llm"] is False
    assert fallback["error_kind"] == "invalid_response"

    async def truncated_post(self, *args, **kwargs):
        return Response({"response": "A partial answer", "done": True, "done_reason": "length"})

    monkeypatch.setattr(Client, "post", truncated_post)
    truncated = asyncio.run(adapter.generate_response("Explain an alert"))
    assert truncated["is_local_llm"] is False
    assert truncated["error_kind"] == "invalid_response"


def test_ollama_timeout_falls_back_without_claiming_model_output(monkeypatch):
    adapter = OllamaAdapter(default_model="gemma4")

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("local model did not respond")

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = asyncio.run(adapter.generate_response("Explain an alert"))
    assert result["is_local_llm"] is False
    assert result["content"] is None
    assert result["error_kind"] == "timeout"
