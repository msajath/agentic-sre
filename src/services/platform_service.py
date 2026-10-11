"""Persistent local runbooks, effective settings, and isolated simulation evaluations."""
from datetime import datetime, timezone
import json
import random
import re
import time
from uuid import uuid4
from src.config import settings, Settings
from src.database import PlatformRecordModel, SessionLocal
from src.models.chaos import ChaosInjectionRequest, FaultType
from src.services.audit_service import audit_service
from src.models.audit import AuditEventType

SCENARIOS = [
    {"id": "SCN-01", "scenario_name": "Service crash", "injected_failure": "SERVICE_CRASH", "target_service": "payment-service", "expected_root_cause": "payment-service", "expected_action": "RESTART_SERVICE", "magnitude": 1},
    {"id": "SCN-02", "scenario_name": "Latency cascade", "injected_failure": "LATENCY", "target_service": "payment-service", "expected_root_cause": "payment-service", "expected_action": "TRIP_CIRCUIT_BREAKER", "magnitude": 2000},
    {"id": "SCN-03", "scenario_name": "Resource saturation", "injected_failure": "RESOURCE_SATURATION", "target_service": "inventory-service", "expected_root_cause": "inventory-service", "expected_action": "SCALE_REPLICAS", "magnitude": 200},
    {"id": "SCN-04", "scenario_name": "Database lock", "injected_failure": "DATABASE_LOCK", "target_service": "payment-service", "expected_root_cause": "payment-service", "expected_action": "TRIP_CIRCUIT_BREAKER", "magnitude": 1},
    {"id": "SCN-05", "scenario_name": "Healthy baseline", "injected_failure": "NONE", "target_service": "notification-service", "expected_root_cause": "NONE", "expected_action": "NOOP", "magnitude": 0},
]

class PlatformService:
    def initialize(self):
        with SessionLocal.begin() as session:
            row = session.get(PlatformRecordModel, "settings")
            if row:
                self._apply_settings(json.loads(row.payload))
            for service, title, content in [
                ("payment-service", "Payment timeout investigation", "Inspect payment error rate and p95 latency. Check upstream callers and active faults. Propose a bounded recovery plan only after identifying the failing service. A lead or administrator must approve the plan. Verify fresh samples for the service and all affected callers before resolving the incident."),
                ("auth-service", "Auth service availability", "Check auth-service availability and heartbeat age. Inspect errors in order-service to distinguish downstream symptoms. Propose a restart when auth availability is lost. Require human approval and verify post-execution latency and errors."),
                ("inventory-service", "Resource saturation investigation", "Inspect CPU and memory utilization in inventory-service. Compare latency and errors with its callers. Scaling is a simulated recovery action in this platform. Require approval and verify healthy post-execution metrics."),
            ]:
                key = f"document:example-{service}"
                if not session.get(PlatformRecordModel, key):
                    document = self._document(f"example-{service}", title, "Example runbook", [service], content)
                    session.add(PlatformRecordModel(key=key, payload=json.dumps(document)))

    @staticmethod
    def _document(doc_id, title, category, target_services, content):
        return {"id": doc_id, "title": title, "category": category, "target_services": target_services,
                "chunk_count": len([chunk for chunk in content.split("\n\n") if chunk.strip()]),
                "embedding_model": "None (local lexical search)", "last_updated": datetime.now(timezone.utc).isoformat(),
                "content_summary": content[:240], "content": content}

    def documents(self):
        with SessionLocal() as session:
            return [json.loads(row.payload) for row in session.query(PlatformRecordModel).filter(PlatformRecordModel.key.startswith("document:")).all()]

    def add_document(self, payload, user):
        document = self._document(uuid4().hex, payload.title, payload.category, payload.target_services, payload.content)
        with SessionLocal.begin() as session:
            session.add(PlatformRecordModel(key=f"document:{document['id']}", payload=json.dumps(document)))
            audit_service.record_event(AuditEventType.INCIDENT_NOTE, user.username, user.role.value,
                                       document["id"], "Added local runbook", {"title": document["title"]}, session)
        return document

    def search(self, query):
        terms = set(re.findall(r"[\w-]+", query.lower()))
        matches = []
        for document in self.documents():
            chunks = [chunk for chunk in document["content"].split("\n\n") if chunk.strip()]
            for chunk in chunks:
                words = set(re.findall(r"[\w-]+", (document["title"] + " " + chunk).lower()))
                score = len(terms & words) / len(terms) if terms else 0
                if score:
                    matches.append({"doc_id": document["id"], "doc_title": document["title"],
                                    "similarity_score": score, "excerpt": chunk[:1200], "target_services": document["target_services"]})
        matches.sort(key=lambda item: item["similarity_score"], reverse=True)
        return {"query": query, "search_method": "lexical term overlap", "total_chunks_matched": len(matches), "citations": matches[:10]}

    @staticmethod
    def _apply_settings(values):
        validated = Settings.model_validate({**settings.model_dump(), **values})
        settings.anomaly_error_rate_threshold = validated.anomaly_error_rate_threshold
        settings.anomaly_latency_p95_ms = validated.anomaly_latency_p95_ms

    def update_settings(self, payload, user):
        values = {"anomaly_error_rate_threshold": payload.error_rate_threshold,
                  "anomaly_latency_p95_ms": payload.latency_p95_threshold_ms}
        Settings.model_validate({**settings.model_dump(), **values})
        with SessionLocal.begin() as session:
            session.merge(PlatformRecordModel(key="settings", payload=json.dumps(values)))
            session.flush()
            audit_service.record_event(AuditEventType.INCIDENT_NOTE, user.username, user.role.value,
                                       "settings", "Updated anomaly thresholds", values, session)
        self._apply_settings(values)
        return self.get_settings()

    @staticmethod
    def get_settings():
        return {"llm_provider": "Optional local Ollama narration; deterministic diagnosis",
                "model_name": settings.ollama_model, "cot_reasoning": False, "temperature": 0.1,
                "error_rate_threshold": settings.anomaly_error_rate_threshold,
                "latency_p95_threshold_ms": settings.anomaly_latency_p95_ms,
                "auto_remediation_low_risk": False, "human_approval_medium_high": True,
                "mode": "simulation" if settings.simulation_enabled else "telemetry-only",
                "kubernetes_execution_available": False, "langgraph_available": False,
                "knowledge_search": "local lexical search"}

    def evaluations(self):
        with SessionLocal() as session:
            runs = [json.loads(row.payload) for row in session.query(PlatformRecordModel).filter(PlatformRecordModel.key.startswith("benchmark:")).all()]
        count = len(runs)
        metrics = {"total_benchmark_runs": count,
                   "root_cause_top1_accuracy": sum(run["diagnosis_result"]["top1_match"] for run in runs) / count if count else None,
                   "tool_selection_accuracy": sum(run["action_match"] for run in runs) / count if count else None,
                   "mean_time_to_diagnose_sec": sum(run["diagnosis_result"]["mttd_sec"] for run in runs) / count if count else None,
                   "mean_time_to_recovery_sec": sum(run["remediation_result"]["mttr_sec"] for run in runs) / count if count else None,
                   "unsafe_action_rate": None}
        catalog = []
        for scenario in SCENARIOS:
            previous = next((run for run in reversed(runs) if run["scenario_id"] == scenario["id"]), None)
            catalog.append({**scenario, "last_run_status": previous["status"] if previous else "NOT_RUN",
                            "mttd_sec": previous["diagnosis_result"]["mttd_sec"] if previous else None,
                            "mttr_sec": previous["remediation_result"]["mttr_sec"] if previous else None,
                            "accuracy_score": float(previous["diagnosis_result"]["top1_match"]) if previous else None})
        return {"metrics": metrics, "scenarios": catalog,
                "measurement_scope": "Isolated synthetic cycles; timings are harness wall-clock durations, not production MTTD/MTTR."}

    def replay(self, scenario_id, user):
        scenario = next((item for item in SCENARIOS if item["id"] == scenario_id), None)
        if scenario is None:
            raise KeyError("Benchmark scenario not found.")
        from src.services.chaos_controller import ChaosController
        from src.services.telemetry_stream import TelemetryStream
        from src.services.simulation_engine import SimulationEngine
        from src.services.anomaly_detector import AnomalyDetector
        from src.services.diagnosis_engine import diagnosis_engine
        from src.services.rule_engine import RuleEngine
        from src.models.correlation import AlertEvent
        chaos = ChaosController()
        telemetry = TelemetryStream(chaos=chaos)
        simulation = SimulationEngine(telemetry=telemetry, chaos=chaos, rng=random.Random(42))
        detector = AnomalyDetector(telemetry=telemetry, persist_incidents=False)
        start = time.perf_counter()
        if scenario["injected_failure"] != "NONE":
            chaos.inject_fault(ChaosInjectionRequest(service_name=scenario["target_service"],
                fault_type=FaultType(scenario["injected_failure"]), magnitude=scenario["magnitude"], duration_sec=60))
        for _ in range(10):
            simulation.simulate_cycle()
        anomalies = detector.evaluate_cluster_health()
        diagnosis = None
        if anomalies:
            alerts = [AlertEvent(timestamp=a.detected_at, service_name=a.service_name, metric_name=a.metric_type,
                                observed_value=a.observed_value, threshold_value=a.threshold_value,
                                severity=a.severity, message=a.description) for a in anomalies]
            diagnosis = diagnosis_engine.diagnose_correlated_alerts(alerts)
        root = diagnosis.root_cause_service if diagnosis else "NONE"
        action = RuleEngine(telemetry=telemetry).evaluate_rules(diagnosis)[0].recommended_action.value if diagnosis else "NOOP"
        diagnosis_sec = time.perf_counter() - start
        recovery_start = time.perf_counter()
        chaos.clear_all_faults()
        for service in settings.managed_services:
            telemetry.flush_service_history(service)
        for _ in range(5):
            simulation.simulate_cycle()
        recovered = not detector.evaluate_cluster_health()
        recovery_sec = time.perf_counter() - recovery_start
        matched = root == scenario["expected_root_cause"]
        action_matched = action == scenario["expected_action"]
        result = {"status": "PASSED" if matched and action_matched and recovered else "FAILED",
                  "scenario_id": scenario_id, "scenario_name": scenario["scenario_name"], "target_service": scenario["target_service"],
                  "diagnosis_result": {"root_cause_identified": root, "top1_match": matched,
                                       "confidence": diagnosis.confidence_score if diagnosis else 0,
                                       "evidence_count": len(anomalies), "mttd_sec": round(diagnosis_sec, 6)},
                  "remediation_result": {"proposed_action": action, "recovered": recovered,
                                         "human_approval_gated": False, "safety_blast_radius_validated": False,
                                         "mttr_sec": round(recovery_sec, 6)},
                  "action_match": action_matched, "simulation": True,
                  "measurement_scope": "Isolated synthetic cycles, no live actions or approval workflow executed.",
                  "evaluated_at": datetime.now(timezone.utc).isoformat()}
        with SessionLocal.begin() as session:
            session.add(PlatformRecordModel(key=f"benchmark:{uuid4().hex}", payload=json.dumps(result)))
            audit_service.record_event(AuditEventType.INCIDENT_NOTE, user.username, user.role.value,
                                       scenario_id, "Ran isolated simulation benchmark", {"status": result["status"]}, session)
        return result

platform_service = PlatformService()
