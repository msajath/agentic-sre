"""
Sliding-Window Temporal and Spatial Event Correlation Engine.
Deduplicates alert storms into unified correlated incident clusters.
"""

from collections import deque
from datetime import datetime, timedelta, timezone
import threading
from typing import Dict, List, Optional
import networkx as nx

from src.models.correlation import (
    AlertEvent,
    CorrelatedIncidentGroup,
    DiagnosticReport,
)
from src.models.incident import AnomalyReport, IncidentSeverity
from src.services.anomaly_detector import anomaly_detector
from src.services.diagnosis_engine import diagnosis_engine
from src.services.topology_graph import topology_engine


class EventCorrelator:
    def __init__(self, window_seconds: int = 25):
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._recent_alerts: deque[AlertEvent] = deque(maxlen=200)
        self._active_groups: Dict[str, CorrelatedIncidentGroup] = {}

    def ingest_anomaly(self, anomaly: AnomalyReport) -> AlertEvent:
        """Converts an anomaly signal into a standard AlertEvent and queues it."""
        alert = AlertEvent(
            timestamp=anomaly.detected_at,
            service_name=anomaly.service_name,
            metric_name=anomaly.metric_type,
            observed_value=anomaly.observed_value,
            threshold_value=anomaly.threshold_value,
            severity=anomaly.severity,
            message=anomaly.description,
        )
        with self._lock:
            self._recent_alerts.append(alert)
        return alert

    def correlate_active_alerts(self) -> List[CorrelatedIncidentGroup]:
        """
        Processes alerts within the sliding temporal window.
        Clusters topologically linked alerts into CorrelatedIncidentGroups.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)

        # 1. First, check latest anomalies from detector
        live_anomalies = anomaly_detector.evaluate_cluster_health()
        for a in live_anomalies:
            self.ingest_anomaly(a)

        with self._lock:
            # Filter alerts within sliding window
            active_alerts = [a for a in self._recent_alerts if a.timestamp >= cutoff]

        if not active_alerts:
            with self._lock:
                self._active_groups.clear()
            return []

        # 2. Cluster alerts spatially using undirected topology graph
        # Services that share direct or transitive caller/callee links belong to the same incident cluster
        undirected_topo = topology_engine.graph.to_undirected()
        
        # Build subgraph of affected services
        affected_services = list({a.service_name for a in active_alerts})
        subgraph = undirected_topo.subgraph(affected_services)
        
        # Connected components represent independent incident clusters!
        connected_clusters = list(nx.connected_components(subgraph))

        new_groups: List[CorrelatedIncidentGroup] = []

        for cluster in connected_clusters:
            cluster_services = set(cluster)
            cluster_alerts = [a for a in active_alerts if a.service_name in cluster_services]

            if not cluster_alerts:
                continue

            # Run diagnosis engine on this cluster
            diagnosis: DiagnosticReport = diagnosis_engine.diagnose_correlated_alerts(cluster_alerts)

            group = CorrelatedIncidentGroup(
                root_cause_service=diagnosis.root_cause_service,
                affected_services=list(cluster_services),
                alert_count=len(cluster_alerts),
                alerts=cluster_alerts,
                diagnosis=diagnosis,
            )
            new_groups.append(group)

        with self._lock:
            self._active_groups = {g.group_id: g for g in new_groups}

        return new_groups

    def get_active_groups(self) -> List[CorrelatedIncidentGroup]:
        """Returns the current list of correlated incident groups."""
        with self._lock:
            return list(self._active_groups.values())


event_correlator = EventCorrelator()
