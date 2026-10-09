"""
Unit & Integration Tests for Incident Lifecycle State Machine and Forensics.
"""

import pytest
from src.models.incident import IncidentSeverity, IncidentState
from src.services.incident_service import incident_service


def test_incident_creation_and_timeline():
    """Verify new incident initialization with genesis timeline event."""
    inc = incident_service.create_incident(
        title="Payment Latency Surge",
        description="Downstream payment gateway latency reached 3500ms",
        severity=IncidentSeverity.HIGH,
        root_cause_service="payment-service",
        affected_services=["payment-service", "order-service"],
        actor="operator",
        actor_role="OPERATOR",
    )

    assert inc.incident_id.startswith("INC-")
    assert inc.state == IncidentState.DETECTED
    assert len(inc.timeline) >= 1
    assert inc.timeline[0].action == "Incident Created"


def test_valid_state_machine_transitions():
    """Verify state machine: DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> RESOLVED."""
    inc = incident_service.create_incident(
        title="Test Cascade Incident",
        description="Testing state transitions",
        severity=IncidentSeverity.MEDIUM,
        actor="lead",
        actor_role="SRE_LEAD",
    )

    # 1. DETECTED -> ACKNOWLEDGED
    inc = incident_service.transition_state(
        inc.incident_id,
        IncidentState.ACKNOWLEDGED,
        reason="Incident acknowledged by on-call engineer",
        actor="operator",
        actor_role="OPERATOR",
    )
    assert inc.state == IncidentState.ACKNOWLEDGED

    # 2. ACKNOWLEDGED -> INVESTIGATING
    inc = incident_service.transition_state(
        inc.incident_id,
        IncidentState.INVESTIGATING,
        reason="Analyzing telemetry logs and service topology",
        actor="lead",
        actor_role="SRE_LEAD",
    )
    assert inc.state == IncidentState.INVESTIGATING

    # 3. INVESTIGATING -> RESOLVED
    inc = incident_service.transition_state(
        inc.incident_id,
        IncidentState.RESOLVED,
        reason="Root cause cleared, health restored",
        actor="lead",
        actor_role="SRE_LEAD",
    )
    assert inc.state == IncidentState.RESOLVED
    assert inc.resolved_at is not None


def test_illegal_state_transition_blocked():
    """Verify illegal lifecycle jumps are rejected."""
    inc = incident_service.create_incident(
        title="Illegal Jump Test",
        description="Attempt invalid state jump",
        severity=IncidentSeverity.LOW,
    )

    # DETECTED cannot jump directly to RESOLVED without acknowledgement/investigation
    with pytest.raises(ValueError) as exc_info:
        incident_service.transition_state(
            inc.incident_id,
            IncidentState.RESOLVED,
            reason="Skip directly to resolved",
            actor="operator",
            actor_role="OPERATOR",
        )
    assert "Illegal lifecycle transition" in str(exc_info.value)


def test_incident_triage_note():
    """Verify adding notes to incident forensic timeline."""
    inc = incident_service.create_incident(
        title="Triage Note Test",
        description="Note addition test",
    )
    updated = incident_service.add_note(
        inc.incident_id,
        note="Inspected Redis connection pool; thread count is normal.",
        actor="operator",
        actor_role="OPERATOR",
    )
    assert any("Inspected Redis connection pool" in event.note for event in updated.timeline)
