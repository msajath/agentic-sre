"""
Unit & Integration Tests for Rule Engine, Remediation Approval Gates, and Recovery Verification.
"""

from datetime import datetime, timezone
import pytest

from src.models.chaos import ChaosInjectionRequest, FaultType
from src.models.correlation import DiagnosticReport, ForensicEvidence
from src.models.incident import IncidentRecord, IncidentSeverity, IncidentState
from src.models.remediation import RemediationActionType, RemediationState
from src.services.chaos_controller import chaos_controller
from src.services.incident_service import incident_service
from src.services.remediation_engine import remediation_engine
from src.services.rule_engine import rule_engine


def test_rule_engine_remediation_recommendation():
    """Verify rule engine recommends restart or circuit breaker on failing payment-service."""
    # Inject fault to create critical condition
    chaos_controller.inject_fault(
        ChaosInjectionRequest(
            service_name="payment-service",
            fault_type=FaultType.SERVICE_CRASH,
            magnitude=1.0,
            duration_sec=30,
        )
    )

    diag = DiagnosticReport(
        root_cause_service="payment-service",
        confidence_score=0.96,
        cascading_symptoms=["order-service"],
        causal_chain=[],
        evidence=ForensicEvidence(
            earliest_fault_timestamp=datetime.now(timezone.utc),
            cascade_delay_ms=250.0,
            causal_path=["payment-service", "order-service"],
            root_cause_metric="availability",
            symptom_signatures=["order-service: 502 Bad Gateway"],
        ),
        recommended_remediation_intent="Restart payment-service",
    )

    rules = rule_engine.evaluate_rules(diag)
    assert len(rules) >= 1
    top_rule = rules[0]
    assert top_rule.target_service == "payment-service"
    assert top_rule.recommended_action in [
        RemediationActionType.RESTART_SERVICE,
        RemediationActionType.ROLLBACK_DEPLOYMENT,
        RemediationActionType.TRIP_CIRCUIT_BREAKER,
    ]

    chaos_controller.clear_all_faults()


def test_remediation_lifecycle_and_recovery_verification():
    """
    Verify full end-to-end workflow:
    1. Incident created
    2. Remediation plan proposed (PENDING_APPROVAL)
    3. SRE Lead approves
    4. Action executes safely
    5. Post-recovery verification passes
    6. Incident is automatically resolved
    """
    # 1. Create incident
    inc = incident_service.create_incident(
        title="Payment Cascade Outage",
        description="Payment container crashed; checkout failing",
        severity=IncidentSeverity.CRITICAL,
        root_cause_service="payment-service",
        affected_services=["payment-service", "order-service"],
    )

    # Inject simulated fault
    chaos_controller.inject_fault(
        ChaosInjectionRequest(
            service_name="payment-service",
            fault_type=FaultType.SERVICE_CRASH,
            magnitude=1.0,
            duration_sec=30,
        )
    )

    # 2. Propose plan
    plan = remediation_engine.propose_plan(
        incident_id=inc.incident_id,
        target_service="payment-service",
        action_type=RemediationActionType.RESTART_SERVICE,
        proposed_by="rule-engine",
    )
    assert plan.state == RemediationState.PENDING_APPROVAL

    # 3. Approve and Execute
    executed_plan = remediation_engine.approve_and_execute(
        plan_id=plan.plan_id,
        approver="lead",
        approver_role="SRE_LEAD",
        reason="Approved by Lead SRE after reviewing cascade impact",
    )

    # 4. Verify post-recovery status
    assert executed_plan.state == RemediationState.VERIFIED_SUCCESSFUL
    assert executed_plan.verified_at is not None

    # 5. Incident must be auto-resolved
    updated_inc = incident_service.get_incident(inc.incident_id)
    assert updated_inc.state == IncidentState.RESOLVED


def test_remediation_rejection():
    """Verify rejection flow."""
    inc = incident_service.create_incident(
        title="False Positive Test",
        description="Spurious alert",
    )
    plan = remediation_engine.propose_plan(
        incident_id=inc.incident_id,
        target_service="auth-service",
        action_type=RemediationActionType.SCALE_REPLICAS,
    )
    rejected = remediation_engine.reject_plan(
        plan_id=plan.plan_id,
        reviewer="lead",
        reviewer_role="SRE_LEAD",
        reason="Load test in progress, scaling not warranted.",
    )
    assert rejected.state == RemediationState.REJECTED
    assert rejected.rejection_reason is not None
