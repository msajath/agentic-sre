"""
Dependency-Aware Root Cause Analysis (RCA) and Forensic Diagnosis Engine.
Evaluates graph topology, temporal sequencing, and error propagation signatures.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import networkx as nx

from src.models.correlation import (
    AlertEvent,
    CausalHop,
    DiagnosticReport,
    ForensicEvidence,
)
from src.services.topology_graph import topology_engine


class DiagnosisEngine:
    def __init__(self):
        pass

    def diagnose_correlated_alerts(
        self,
        alerts: List[AlertEvent],
        incident_id: Optional[str] = None,
    ) -> DiagnosticReport:
        """
        Analyzes a cluster of alerts to produce a forensic DiagnosticReport.
        Identifies root cause service, computes confidence score, and traces causal hops.
        """
        if not alerts:
            raise ValueError("Cannot diagnose an empty alert collection.")

        # Group alerts by service
        alerts_by_service: Dict[str, List[AlertEvent]] = {}
        for a in alerts:
            alerts_by_service.setdefault(a.service_name, []).append(a)

        affected_services = list(alerts_by_service.keys())

        # 1. Topological Root Cause Detection
        # A service is a root cause candidate if none of its downstream dependencies in the topology are degraded
        root_cause_service = None
        for svc in affected_services:
            downstream = topology_engine.get_downstream_dependencies(svc)
            # If no downstream service called by `svc` is also degraded, `svc` is failing from within!
            if not any(dep in affected_services for dep in downstream):
                root_cause_service = svc
                break

        if not root_cause_service:
            # Fallback to the service with the earliest alert timestamp
            sorted_by_time = sorted(alerts, key=lambda a: a.timestamp)
            root_cause_service = sorted_by_time[0].service_name

        # 2. Separate symptoms from root cause
        symptoms = [s for s in affected_services if s != root_cause_service]

        # 3. Trace Causal Chain (Paths in topology graph from root cause to callers)
        causal_hops: List[CausalHop] = []
        causal_path = [root_cause_service]
        
        # In call graph: caller -> callee (e.g. order-service -> payment-service)
        # So in reverse graph: root_cause -> caller
        rev_graph = topology_engine.graph.reverse()
        for symptom_svc in symptoms:
            if nx.has_path(rev_graph, root_cause_service, symptom_svc):
                path = nx.shortest_path(rev_graph, root_cause_service, symptom_svc)
                for i in range(len(path) - 1):
                    src_node = path[i]
                    tgt_node = path[i + 1]
                    causal_hops.append(
                        CausalHop(
                            from_service=src_node,
                            to_service=tgt_node,
                            impact_description=f"Outage in '{src_node}' caused cascading failure in dependent caller '{tgt_node}'",
                        )
                    )
                causal_path = path

        # 4. Forensic Evidence Construction
        sorted_alerts = sorted(alerts, key=lambda a: a.timestamp)
        earliest_time = sorted_alerts[0].timestamp
        latest_time = sorted_alerts[-1].timestamp
        cascade_delay = max(0.0, (latest_time - earliest_time).total_seconds() * 1000.0)

        root_alerts = alerts_by_service.get(root_cause_service, [])
        root_metric = root_alerts[0].metric_name if root_alerts else "unknown"

        symptom_signatures = []
        for s in symptoms:
            s_alerts = alerts_by_service.get(s, [])
            for sa in s_alerts:
                symptom_signatures.append(f"{s}: {sa.metric_name} ({sa.message})")

        evidence = ForensicEvidence(
            earliest_fault_timestamp=earliest_time,
            cascade_delay_ms=round(cascade_delay, 1),
            causal_path=causal_path,
            root_cause_metric=root_metric,
            symptom_signatures=symptom_signatures,
        )

        # 5. Confidence Score Calculation
        confidence = 0.85
        if symptoms:
            # If multiple callers degraded downstream, confidence is higher
            confidence = min(0.98, 0.85 + (len(symptoms) * 0.05))
        if len(causal_hops) > 0:
            confidence = min(0.99, confidence + 0.04)

        # 6. Recommended Remediation Intent
        if "crash" in root_metric.lower() or "availability" in root_metric.lower():
            remediation = f"Restart pod/container for [{root_cause_service}] and verify health probes."
        elif "latency" in root_metric.lower():
            remediation = f"Scale up replicas for [{root_cause_service}] or trip circuit-breaker on upstream callers."
        elif "error" in root_metric.lower():
            remediation = f"Roll back recent deployment or apply circuit-breaker fallback for [{root_cause_service}]."
        else:
            remediation = f"Restart [{root_cause_service}] service instances."

        return DiagnosticReport(
            incident_id=incident_id,
            root_cause_service=root_cause_service,
            confidence_score=round(confidence, 2),
            cascading_symptoms=symptoms,
            causal_chain=causal_hops,
            evidence=evidence,
            recommended_remediation_intent=remediation,
        )


diagnosis_engine = DiagnosisEngine()
