"""
Enterprise Microservice Simulation Engine.
Generates realistic multi-tier traffic flows and accurately simulates cascading failures across dependent services.
"""

import asyncio
from datetime import datetime, timezone
import random
from typing import Optional

from src.models.chaos import FaultType
from src.models.telemetry import HeartbeatPayload, ServiceStatus, TelemetryPoint
from src.services.chaos_controller import chaos_controller
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine


class SimulationEngine:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Starts asynchronous simulation background loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._simulation_loop())

    def stop(self):
        """Stops background simulation."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _simulation_loop(self):
        """Continuous simulation cycle generating events and heartbeats."""
        while self._running:
            try:
                self.simulate_cycle()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue to keep platform resilient
                print(f"[SimulationEngine Error] {e}")
                await asyncio.sleep(1.0)

    def simulate_cycle(self):
        """
        Executes one discrete simulation step:
        Emits synthetic telemetry points and heartbeats according to current operational conditions.
        """
        now = datetime.now(timezone.utc)

        # 1. Simulate Auth Service (Security Tier)
        auth_fault = chaos_controller.is_fault_active("auth-service", FaultType.SERVICE_CRASH)
        auth_error = chaos_controller.is_fault_active("auth-service", FaultType.ERROR_STORM)
        auth_latency = chaos_controller.is_fault_active("auth-service", FaultType.LATENCY)
        
        auth_status_code = 200
        auth_lat = random.uniform(8.0, 25.0)
        auth_status = ServiceStatus.HEALTHY
        
        if auth_fault:
            auth_status_code = 503
            auth_lat = 5.0
            auth_status = ServiceStatus.DOWN
        elif auth_error:
            if random.random() < (auth_error.magnitude / 100.0 if auth_error.magnitude <= 100 else 0.8):
                auth_status_code = 500
            auth_status = ServiceStatus.DEGRADED
        elif auth_latency:
            auth_lat += auth_latency.magnitude
            auth_status = ServiceStatus.DEGRADED

        telemetry_stream.record_telemetry(TelemetryPoint(
            timestamp=now,
            service_name="auth-service",
            endpoint="/api/v1/auth/verify",
            status_code=auth_status_code,
            latency_ms=round(auth_lat, 2),
            cpu_usage_pct=round(random.uniform(15.0, 35.0), 1),
            memory_usage_pct=round(random.uniform(25.0, 45.0), 1),
        ))
        telemetry_stream.record_heartbeat(HeartbeatPayload(
            service_name="auth-service",
            timestamp=now,
            status=auth_status,
            active_instances=3 if auth_status != ServiceStatus.DOWN else 0,
        ))

        # 2. Simulate Payment Service (Financial Gateway Tier)
        pay_fault = chaos_controller.is_fault_active("payment-service", FaultType.SERVICE_CRASH)
        pay_error = chaos_controller.is_fault_active("payment-service", FaultType.ERROR_STORM)
        pay_latency = chaos_controller.is_fault_active("payment-service", FaultType.LATENCY)
        pay_lock = chaos_controller.is_fault_active("payment-service", FaultType.DATABASE_LOCK)
        
        pay_status_code = 200
        pay_lat = random.uniform(40.0, 110.0)
        pay_status = ServiceStatus.HEALTHY

        if pay_fault:
            pay_status_code = 503
            pay_lat = 10.0
            pay_status = ServiceStatus.DOWN
        elif pay_error:
            prob = pay_error.magnitude / 100.0 if pay_error.magnitude <= 100 else 0.8
            if random.random() < prob:
                pay_status_code = 500
            pay_status = ServiceStatus.DEGRADED
        elif pay_latency:
            pay_lat += pay_latency.magnitude
            pay_status = ServiceStatus.DEGRADED
        elif pay_lock:
            pay_lat += 2500.0
            if random.random() < 0.5:
                pay_status_code = 504
            pay_status = ServiceStatus.CRITICAL

        telemetry_stream.record_telemetry(TelemetryPoint(
            timestamp=now,
            service_name="payment-service",
            endpoint="/api/v1/payments/charge",
            status_code=pay_status_code,
            latency_ms=round(pay_lat, 2),
            cpu_usage_pct=round(random.uniform(20.0, 50.0) + (40.0 if pay_lock else 0.0), 1),
            memory_usage_pct=round(random.uniform(30.0, 60.0), 1),
        ))
        telemetry_stream.record_heartbeat(HeartbeatPayload(
            service_name="payment-service",
            timestamp=now,
            status=pay_status,
            active_instances=2 if pay_status != ServiceStatus.DOWN else 0,
        ))

        # 3. Simulate Inventory Service (Catalog Tier)
        inv_fault = chaos_controller.is_fault_active("inventory-service", FaultType.SERVICE_CRASH)
        inv_error = chaos_controller.is_fault_active("inventory-service", FaultType.ERROR_STORM)
        inv_latency = chaos_controller.is_fault_active("inventory-service", FaultType.LATENCY)

        inv_status_code = 200
        inv_lat = random.uniform(15.0, 45.0)
        inv_status = ServiceStatus.HEALTHY

        if inv_fault:
            inv_status_code = 503
            inv_lat = 5.0
            inv_status = ServiceStatus.DOWN
        elif inv_error:
            if random.random() < (inv_error.magnitude / 100.0 if inv_error.magnitude <= 100 else 0.8):
                inv_status_code = 500
            inv_status = ServiceStatus.DEGRADED
        elif inv_latency:
            inv_lat += inv_latency.magnitude
            inv_status = ServiceStatus.DEGRADED

        telemetry_stream.record_telemetry(TelemetryPoint(
            timestamp=now,
            service_name="inventory-service",
            endpoint="/api/v1/inventory/reserve",
            status_code=inv_status_code,
            latency_ms=round(inv_lat, 2),
            cpu_usage_pct=round(random.uniform(10.0, 30.0), 1),
            memory_usage_pct=round(random.uniform(20.0, 40.0), 1),
        ))
        telemetry_stream.record_heartbeat(HeartbeatPayload(
            service_name="inventory-service",
            timestamp=now,
            status=inv_status,
            active_instances=2 if inv_status != ServiceStatus.DOWN else 0,
        ))

        # 4. Simulate Order Service (Core Orchestrator - CASCADES from Auth, Payment, Inventory)
        order_fault = chaos_controller.is_fault_active("order-service", FaultType.SERVICE_CRASH)
        order_own_error = chaos_controller.is_fault_active("order-service", FaultType.ERROR_STORM)
        order_own_latency = chaos_controller.is_fault_active("order-service", FaultType.LATENCY)

        order_status_code = 200
        # Base latency is sum of its internal processing plus downstream calls
        order_lat = random.uniform(25.0, 60.0) + (pay_lat * 0.9) + (inv_lat * 0.4) + (auth_lat * 0.2)
        order_status = ServiceStatus.HEALTHY

        # Cascading Failure Logic:
        # If Payment is Down or Erroring, Orders fail with 502/500/504!
        if order_fault:
            order_status_code = 503
            order_lat = 5.0
            order_status = ServiceStatus.DOWN
        elif auth_status_code >= 500 or auth_status == ServiceStatus.DOWN:
            # Cascading effect from Auth failure
            order_status_code = 502
            order_status = ServiceStatus.DEGRADED
        elif pay_status_code >= 500 or pay_status == ServiceStatus.DOWN:
            # Cascading effect from Payment failure
            order_status_code = 502 if pay_status_code == 500 else 504
            order_status = ServiceStatus.CRITICAL
        elif inv_status_code >= 500 or inv_status == ServiceStatus.DOWN:
            # Cascading effect from Inventory failure
            order_status_code = 502
            order_status = ServiceStatus.DEGRADED
        elif order_own_error:
            order_status_code = 500
            order_status = ServiceStatus.DEGRADED
        elif order_own_latency:
            order_lat += order_own_latency.magnitude
            order_status = ServiceStatus.DEGRADED
        elif order_lat > 1000.0:
            order_status = ServiceStatus.DEGRADED

        telemetry_stream.record_telemetry(TelemetryPoint(
            timestamp=now,
            service_name="order-service",
            endpoint="/api/v1/orders/checkout",
            status_code=order_status_code,
            latency_ms=round(order_lat, 2),
            cpu_usage_pct=round(random.uniform(30.0, 65.0), 1),
            memory_usage_pct=round(random.uniform(35.0, 60.0), 1),
            error_message="Downstream dependency failure" if order_status_code >= 500 and not order_fault and not order_own_error else None,
        ))
        telemetry_stream.record_heartbeat(HeartbeatPayload(
            service_name="order-service",
            timestamp=now,
            status=order_status,
            active_instances=4 if order_status != ServiceStatus.DOWN else 0,
        ))

        # 5. Simulate Notification Service (Consumes Order Events)
        notif_fault = chaos_controller.is_fault_active("notification-service", FaultType.SERVICE_CRASH)
        notif_lat = random.uniform(10.0, 30.0)
        notif_status_code = 200
        notif_status = ServiceStatus.HEALTHY

        if notif_fault:
            notif_status_code = 503
            notif_status = ServiceStatus.DOWN
        
        telemetry_stream.record_telemetry(TelemetryPoint(
            timestamp=now,
            service_name="notification-service",
            endpoint="/api/v1/notifications/send",
            status_code=notif_status_code,
            latency_ms=round(notif_lat, 2),
            cpu_usage_pct=round(random.uniform(10.0, 25.0), 1),
            memory_usage_pct=round(random.uniform(15.0, 30.0), 1),
        ))
        telemetry_stream.record_heartbeat(HeartbeatPayload(
            service_name="notification-service",
            timestamp=now,
            status=notif_status,
            active_instances=2 if notif_status != ServiceStatus.DOWN else 0,
        ))


simulation_engine = SimulationEngine()
