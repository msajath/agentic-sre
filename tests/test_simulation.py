"""
Unit and Integration Tests for Microservice Simulation and Cascading Failures.
"""

import pytest
from src.models.chaos import ChaosInjectionRequest, FaultType
from src.services.chaos_controller import chaos_controller
from src.services.simulation_engine import simulation_engine
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine


def test_topology_initialization():
    """Ensure all required enterprise services and edges are properly configured."""
    topo = topology_engine.get_topology()
    service_ids = {n.id for n in topo.nodes}

    expected_services = {
        "auth-service",
        "inventory-service",
        "payment-service",
        "order-service",
        "notification-service",
    }
    assert expected_services.issubset(service_ids)

    # Order service must depend on Auth, Payment, and Inventory
    order_deps = set(topology_engine.get_downstream_dependencies("order-service"))
    assert {"auth-service", "payment-service", "inventory-service"}.issubset(order_deps)


def test_cascading_failure_propagation():
    """
    Test cascade effect: Injecting a crash into payment-service
    must cascade outward and degrade order-service.
    """
    chaos_controller.clear_all_faults()

    # Inject failure into payment-service
    chaos_controller.inject_fault(
        ChaosInjectionRequest(
            service_name="payment-service",
            fault_type=FaultType.SERVICE_CRASH,
            magnitude=1.0,
            duration_sec=30,
        )
    )

    # Run simulation cycle
    simulation_engine.simulate_cycle()

    # Check order service telemetry
    order_points = telemetry_stream.get_recent_points("order-service", limit=1)
    assert len(order_points) == 1
    recent_order_event = order_points[0]

    # Order service must have failed because payment was down!
    assert recent_order_event.status_code in [502, 504]

    # Clean up
    chaos_controller.clear_all_faults()
