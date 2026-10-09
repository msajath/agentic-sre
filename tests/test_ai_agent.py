"""
Unit Tests for Agentic AI Reasoning Orchestrator.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.correlation import CausalHop, DiagnosticReport, ForensicEvidence
from src.models.incident import IncidentSeverity
from src.models.remediation import RemediationActionType
from src.services.ai_agent import sre_ai_agent
from src.services.incident_service import incident_service

client = TestClient(app)


def test_ai_status_endpoint():
    """Verify AI status endpoint responds with operational agent info."""
    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["chain_of_thought_enabled"] is True
    assert data["human_in_the_loop_checkpoint"] is True


def test_ai_agent_reasoning_orchestrator():
    """Verify multi-step chain-of-thought AI diagnosis formulation."""
    report = DiagnosticReport(
        incident_id="INC-AI-TEST",
        root_cause_service="payment-service",
        confidence_score=0.95,
        cascading_symptoms=["order-service"],
        causal_chain=[
            CausalHop(
                from_service="payment-service",
                to_service="order-service",
                relation="calls",
                impact_description="Downstream payment timeout cascades to order service",
            )
        ],
        evidence=ForensicEvidence(
            earliest_fault_timestamp=datetime.now(timezone.utc),
            cascade_delay_ms=320.0,
            causal_path=["payment-service", "order-service"],
            root_cause_metric="high_error_rate",
            symptom_signatures=["order-service: cascading 503"],
        ),
        recommended_remediation_intent="Restart service",
    )

    hypothesis = sre_ai_agent.run_agentic_diagnosis("INC-AI-TEST", report)
    assert hypothesis.root_cause_service == "payment-service"
    assert hypothesis.confidence == 0.95
    assert len(hypothesis.mitigation_steps) == 4
    assert "[Agent Step 1: Ingestion]" in hypothesis.explanation
    assert "[Agent Step 4: Blast Radius Containment]" in hypothesis.explanation
    assert hypothesis.recommended_action == RemediationActionType.RESTART_SERVICE


def test_ai_analyze_incident_api():
    """Verify API endpoint triggers AI reasoning on incident."""
    inc = incident_service.create_incident(
        title="Payment Gateway Timeout",
        description="Downstream timeout cascades to order service",
        severity=IncidentSeverity.HIGH,
        affected_services=["payment-service", "order-service"],
        root_cause_service="payment-service",
    )

    response = client.post(f"/api/v1/ai/analyze-incident/{inc.incident_id}")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["root_cause_service"] == "payment-service"
    assert "explanation" in res_data
    assert len(res_data["mitigation_steps"]) > 0
