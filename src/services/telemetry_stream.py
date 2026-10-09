"""
Telemetry Stream Ingestion and Rolling Window Aggregator.
Guarantees high throughput and bounded memory usage via fixed-size circular deques.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional
import threading

from src.models.telemetry import (
    HeartbeatPayload,
    ServiceMetricsSummary,
    ServiceStatus,
    TelemetryPoint,
)
from src.services.chaos_controller import chaos_controller
from src.config import settings


class TelemetryStream:
    def __init__(self, window_size: int = settings.telemetry_window_size):
        self.window_size = window_size
        self._lock = threading.Lock()
        # Per-service rolling windows of raw telemetry points
        self._history: Dict[str, deque[TelemetryPoint]] = {}
        # Last known heartbeats
        self._last_heartbeat: Dict[str, HeartbeatPayload] = {}
        
        # Initialize tracked services
        for svc in settings.managed_services:
            self._history[svc] = deque(maxlen=self.window_size)

    def record_telemetry(self, point: TelemetryPoint) -> None:
        """Appends a validated telemetry data point."""
        with self._lock:
            if point.service_name not in self._history:
                self._history[point.service_name] = deque(maxlen=self.window_size)
            self._history[point.service_name].append(point)

    def record_heartbeat(self, heartbeat: HeartbeatPayload) -> None:
        """Records a service heartbeat timestamp and health status."""
        with self._lock:
            self._last_heartbeat[heartbeat.service_name] = heartbeat

    def flush_service_history(self, service_name: str) -> None:
        """Flushes rolling historical buffer on service restart / recovery."""
        with self._lock:
            if service_name in self._history:
                self._history[service_name].clear()

    def get_service_summary(self, service_name: str) -> ServiceMetricsSummary:
        """Computes statistical summary for the service across its current window."""
        with self._lock:
            points = list(self._history.get(service_name, []))
            hb = self._last_heartbeat.get(service_name)

        active_faults = chaos_controller.get_active_faults(service_name)
        fault_names = [f.fault_type.value for f in active_faults]

        total_requests = len(points)
        if total_requests == 0:
            return ServiceMetricsSummary(
                service_name=service_name,
                status=ServiceStatus.HEALTHY if not active_faults else ServiceStatus.DEGRADED,
                total_requests=0,
                error_count=0,
                error_rate=0.0,
                avg_latency_ms=15.0,
                p95_latency_ms=25.0,
                cpu_usage_pct=10.0,
                memory_usage_pct=20.0,
                active_faults=fault_names,
                last_heartbeat=hb.timestamp if hb else None,
            )

        errors = [p for p in points if p.status_code >= 500]
        error_count = len(errors)
        error_rate = error_count / total_requests

        latencies = sorted(p.latency_ms for p in points)
        avg_latency = sum(latencies) / total_requests
        p95_index = int(0.95 * total_requests)
        p95_latency = latencies[min(p95_index, total_requests - 1)]

        avg_cpu = sum(p.cpu_usage_pct for p in points) / total_requests
        avg_mem = sum(p.memory_usage_pct for p in points) / total_requests

        # Determine health status based on metrics & faults
        if any(f.fault_type.value == "SERVICE_CRASH" for f in active_faults):
            status = ServiceStatus.DOWN
        elif error_rate > 0.40 or p95_latency > 3000.0:
            status = ServiceStatus.CRITICAL
        elif error_rate > settings.anomaly_error_rate_threshold or p95_latency > settings.anomaly_latency_p95_ms:
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.HEALTHY

        return ServiceMetricsSummary(
            service_name=service_name,
            status=status,
            total_requests=total_requests,
            error_count=error_count,
            error_rate=round(error_rate, 4),
            avg_latency_ms=round(avg_latency, 2),
            p95_latency_ms=round(p95_latency, 2),
            cpu_usage_pct=round(avg_cpu, 1),
            memory_usage_pct=round(avg_mem, 1),
            active_faults=fault_names,
            last_heartbeat=hb.timestamp if hb else None,
        )

    def get_all_summaries(self) -> List[ServiceMetricsSummary]:
        """Returns summaries for all monitored services in the cluster."""
        return [self.get_service_summary(svc) for svc in settings.managed_services]

    def get_recent_points(self, service_name: str, limit: int = 50) -> List[TelemetryPoint]:
        """Fetches the latest N telemetry events for diagnostics."""
        with self._lock:
            points = list(self._history.get(service_name, []))
            return points[-limit:]


telemetry_stream = TelemetryStream()
