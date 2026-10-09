"""
Rule-Based Root Cause Diagnostic Engine.
Evaluates deterministic SRE incident rules to produce ranked remediation hypotheses.
"""

from typing import List, Optional

from src.models.correlation import DiagnosticReport
from src.models.remediation import RemediationActionType, RuleEvaluationResult
from src.services.telemetry_stream import telemetry_stream


class RuleEngine:
    def evaluate_rules(self, diagnosis: DiagnosticReport) -> List[RuleEvaluationResult]:
        """
        Evaluates heuristic and deterministic rules against the diagnosed incident context.
        Returns ranked evaluation results and recommended actions.
        """
        results: List[RuleEvaluationResult] = []
        svc = diagnosis.root_cause_service
        summary = telemetry_stream.get_service_summary(svc)

        # Rule 1: Service Outage / Container Crash
        if summary.status.value in ["DOWN", "CRITICAL"] and summary.error_rate >= 0.50:
            results.append(
                RuleEvaluationResult(
                    rule_id="RULE-CRASH-01",
                    rule_name="Service Crash & Availability Loss",
                    matched=True,
                    confidence=0.96,
                    diagnosis_summary=f"Service '{svc}' is experiencing critical availability outage (>50% error rate).",
                    recommended_action=RemediationActionType.RESTART_SERVICE,
                    target_service=svc,
                )
            )

        # Rule 2: Cascading Downstream Saturation
        if diagnosis.cascading_symptoms and summary.p95_latency_ms >= 1000.0:
            results.append(
                RuleEvaluationResult(
                    rule_id="RULE-CASCADE-02",
                    rule_name="Cascading Downstream Latency Choke",
                    matched=True,
                    confidence=0.92,
                    diagnosis_summary=f"Latency spike in '{svc}' is cascading outward to callers {diagnosis.cascading_symptoms}.",
                    recommended_action=RemediationActionType.TRIP_CIRCUIT_BREAKER,
                    target_service=svc,
                )
            )

        # Rule 3: High Resource Load / Concurrency Exhaustion
        if summary.cpu_usage_pct >= 60.0 or summary.memory_usage_pct >= 60.0:
            results.append(
                RuleEvaluationResult(
                    rule_id="RULE-SCALE-03",
                    rule_name="Compute & Worker Saturation",
                    matched=True,
                    confidence=0.88,
                    diagnosis_summary=f"Compute resource utilization high on '{svc}' (CPU: {summary.cpu_usage_pct}%, Mem: {summary.memory_usage_pct}%).",
                    recommended_action=RemediationActionType.SCALE_REPLICAS,
                    target_service=svc,
                )
            )

        # Rule 4: Software Defect / Regressed Build
        if summary.error_rate > 0.15 and not any(r.rule_id == "RULE-CRASH-01" for r in results):
            results.append(
                RuleEvaluationResult(
                    rule_id="RULE-REGRESS-04",
                    rule_name="Deployment Regression / Error Storm",
                    matched=True,
                    confidence=0.85,
                    diagnosis_summary=f"Persistent internal application 500 errors observed on '{svc}'.",
                    recommended_action=RemediationActionType.ROLLBACK_DEPLOYMENT,
                    target_service=svc,
                )
            )

        # Fallback default rule if no specific rule matched
        if not results:
            results.append(
                RuleEvaluationResult(
                    rule_id="RULE-GENERIC-00",
                    rule_name="Standard Health Recovery",
                    matched=True,
                    confidence=0.75,
                    diagnosis_summary=f"General operational anomaly detected on '{svc}'.",
                    recommended_action=RemediationActionType.RESTART_SERVICE,
                    target_service=svc,
                )
            )

        # Sort by confidence descending
        return sorted(results, key=lambda r: r.confidence, reverse=True)


rule_engine = RuleEngine()
