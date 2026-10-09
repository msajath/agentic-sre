"""
Unit Tests for Chaos Controller, Fault Invalidation, and Blast Radius Calculation.
"""

import pytest
from src.models.chaos import ChaosInjectionRequest, FaultType
from src.services.chaos_controller import chaos_controller
from src.services.topology_graph import topology_engine


def test_fault_injection_and_removal():
    """Verify fault lifecycle: inject, check active, remove."""
    req = ChaosInjectionRequest(
        service_name="inventory-service",
        fault_type=FaultType.LATENCY,
        magnitude=1500.0,
        duration_sec=20,
    )
    fault = chaos_controller.inject_fault(req)
    assert fault.is_active is True
    assert fault.service_name == "inventory-service"

    active = chaos_controller.get_active_faults("inventory-service")
    assert len(active) == 1
    assert active[0].fault_type == FaultType.LATENCY

    # Clear fault
    cleared = chaos_controller.remove_fault("inventory-service")
    assert len(cleared) >= 1
    assert len(chaos_controller.get_active_faults("inventory-service")) == 0


def test_invalid_service_injection_blocked():
    """Ensures unauthorized/non-existent services cannot receive fault injection."""
    req = ChaosInjectionRequest(
        service_name="unknown-hacker-service",
        fault_type=FaultType.SERVICE_CRASH,
        magnitude=1.0,
        duration_sec=30,
    )
    with pytest.raises(ValueError):
        chaos_controller.inject_fault(req)


def test_blast_radius_calculation():
    """Verify topology engine accurately calculates upstream blast radius."""
    # If payment-service fails, order-service (and transitively notification-service) are affected
    affected = topology_engine.get_affected_dependents("payment-service")
    assert "order-service" in affected
