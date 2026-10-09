"""
Real-time Anomaly Detection and Cascading Failure Evaluator.
Distinguishes initial trigger point from cascading symptoms across interconnected services.
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.models.incident import AnomalyReport, IncidentRecord, IncidentSeverity, IncidentState
from src.models.telemetry import ServiceStatus
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine
from src.config import settings


class AnomalyDetector:
    def __init__(self):
        self._active_anomalies: List[AnomalyReport] = []

    def evaluate_cluster_health(self) -> List[AnomalyReport]:
        """
        Scans all services in cluster to detect active anomalies against thresholds.
        """
        anomalies: List[AnomalyReport] = []
        now = datetime.now(timezone.utc)
        summaries = telemetry_stream.get_all_summaries()

        for summary in summaries:
            # 1. Error Rate Anomaly
            if summary.error_rate > settings.anomaly_error_rate_threshold:
                severity = IncidentSeverity.CRITICAL if summary.error_rate > 0.40 else IncidentSeverity.HIGH
                anomalies.append(
                    AnomalyReport(
                        service_name=summary.service_name,
                        metric_type="error_rate",
                        observed_value=summary.error_rate,
                        threshold_value=settings.anomaly_error_rate_threshold,
                        description=f"Error rate elevated at {summary.error_rate * 100:.1f}% (Threshold: {settings.anomaly_error_rate_threshold * 100:.1f}%)",
                        detected_at=now,
                        severity=severity,
                    )
                )

            # 2. Latency p95 Anomaly
            if summary.p95_latency_ms > settings.anomaly_latency_p95_ms:
                severity = IncidentSeverity.HIGH if summary.p95_latency_ms > 2000.0 else IncidentSeverity.MEDIUM
                anomalies.append(
                    AnomalyReport(
                        service_name=summary.service_name,
                        metric_type="p95_latency",
                        observed_value=summary.p95_latency_ms,
                        threshold_value=settings.anomaly_latency_p95_ms,
                        description=f"High p95 latency: {summary.p95_latency_ms:.1f}ms exceeds threshold {settings.anomaly_latency_p95_ms:.1f}ms",
                        detected_at=now,
                        severity=severity,
                    )
                )

            # 3. Complete Service Outage
            if summary.status == ServiceStatus.DOWN:
                anomalies.append(
                    AnomalyReport(
                        service_name=summary.service_name,
                        metric_type="availability",
                        observed_value=0.0,
                        threshold_value=1.0,
                        description=f"Service '{summary.service_name}' is completely DOWN (Zero healthy instances or 503 response)",
                        detected_at=now,
                        severity=IncidentSeverity.CRITICAL,
                    )
                )

        self._active_anomalies = anomalies
        return anomalies

    def identify_potential_incident(self) -> Optional[IncidentRecord]:
        """
        Correlates multiple anomalies into a single incident candidate,
        identifying the most probable root cause service using graph topology.
        """
        anomalies = self.evaluate_cluster_health()
        if not anomalies:
            return None

        affected_services = list({a.service_name for a in anomalies})
        
        # Determine root cause candidate:
        # A service that does NOT depend on any other currently degraded service is the root!
        root_candidate = None
        for svc in affected_services:
            downstream = topology_engine.get_downstream_dependencies(svc)
            # If none of its downstream dependencies are degraded, this service is self-failing!
            if not any(dep in affected_services for dep in downstream):
                root_candidate = svc
                break

        if not root_candidate and affected_services:
            root_candidate = affected_services[0]

        highest_severity = IncidentSeverity.MEDIUM
        for a in anomalies:
            if a.severity == IncidentSeverity.CRITICAL:
                highest_severity = IncidentSeverity.CRITICAL
                break
            elif a.severity == IncidentSeverity.HIGH:
                highest_severity = IncidentSeverity.HIGH

        return IncidentRecord(
            title=f"Cascading Degradation Originating from [{root_candidate}]" if len(affected_services) > 1 else f"Service Degraded: [{root_candidate}]",
            description=f"{len(anomalies)} anomalies detected across {len(affected_services)} services. Blast radius: {', '.join(affected_services)}",
            state=IncidentState.DETECTED,
            severity=highest_severity,
            root_cause_service=root_candidate,
            affected_services=affected_services,
            anomalies=anomalies,
        )


anomaly_detector = AnomalyDetector()
