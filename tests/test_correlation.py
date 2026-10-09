"""
Unit & Integration Tests for Event Correlation, Causal Path Traversal, and Dependency-Aware RCA.
"""

from datetime import datetime, timezone
import pytest

from src.models.correlation import AlertEvent
from src.models.incident import IncidentSeverity
from src.services.diagnosis_engine import diagnosis_engine
from src.services.event_correlator import event_correlator


def test_correlate_cascading_alerts():
    """
    Simulate an alert storm where payment-service fails first,
    and order-service degrades as a consequence.
    """
    now = datetime.now(timezone.utc)

    # 1. Root failure alert in payment-service
    alert_payment = AlertEvent(
        timestamp=now,
        service_name="payment-service",
        metric_name="error_rate",
        observed_value=0.85,
        threshold_value=0.05,
        severity=IncidentSeverity.CRITICAL,
        message="Payment gateway returning HTTP 500 storm",
    )

    # 2. Downstream consequence in order-service
    alert_order = AlertEvent(
        timestamp=now,
        service_name="order-service",
        metric_name="p95_latency",
        observed_value=2400.0,
        threshold_value=800.0,
        severity=IncidentSeverity.HIGH,
        message="Order checkout experiencing downstream timeout",
    )

    alerts = [alert_payment, alert_order]

    # Run Diagnosis Engine
    report = diagnosis_engine.diagnose_correlated_alerts(alerts)

    # Assertions
    assert report.root_cause_service == "payment-service"
    assert "order-service" in report.cascading_symptoms
    assert report.confidence_score >= 0.85
    assert len(report.causal_chain) >= 1
    assert report.causal_chain[0].from_service == "payment-service"
    assert report.causal_chain[0].to_service == "order-service"
    assert "payment-service" in report.recommended_remediation_intent


def test_isolated_single_alert_diagnosis():
    """Verify diagnosis on a single non-cascading alert."""
    alert = AlertEvent(
        service_name="auth-service",
        metric_name="availability",
        observed_value=0.0,
        threshold_value=1.0,
        severity=IncidentSeverity.CRITICAL,
        message="Auth service container terminated unexpectedly",
    )

    report = diagnosis_engine.diagnose_correlated_alerts([alert])
    assert report.root_cause_service == "auth-service"
    assert len(report.cascading_symptoms) == 0
    assert report.confidence_score >= 0.80
    assert "auth-service" in report.recommended_remediation_intent
