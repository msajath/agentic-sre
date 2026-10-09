"""
Unit Tests for Telemetry Ingestion, Validation, and Metric Aggregation.
"""

import pytest
from pydantic import ValidationError
from src.models.telemetry import TelemetryPoint
from src.services.telemetry_stream import telemetry_stream


def test_telemetry_valid_point():
    """Verify clean ingestion and sanitization."""
    point = TelemetryPoint(
        service_name="ORDER-SERVICE",  # uppercase should be sanitized to lowercase
        endpoint="/api/v1/orders/checkout",
        status_code=200,
        latency_ms=45.2,
        cpu_usage_pct=25.0,
        memory_usage_pct=40.0,
    )
    assert point.service_name == "order-service"
    telemetry_stream.record_telemetry(point)

    summary = telemetry_stream.get_service_summary("order-service")
    assert summary.total_requests >= 1


def test_telemetry_invalid_metrics_rejected():
    """Verify input validation protects against malicious/corrupt payloads."""
    # Negative latency should be rejected
    with pytest.raises(ValidationError):
        TelemetryPoint(service_name="auth-service", latency_ms=-10.0)

    # Invalid status code
    with pytest.raises(ValidationError):
        TelemetryPoint(service_name="auth-service", status_code=999)

    # Malicious service name with script tag / path traversal
    with pytest.raises(ValidationError):
        TelemetryPoint(service_name="auth<script>alert(1)</script>")
