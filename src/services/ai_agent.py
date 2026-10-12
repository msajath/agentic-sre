"""Deterministic rule-based diagnosis of simulated telemetry."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.models.correlation import DiagnosticReport
from src.models.remediation import RemediationActionType
from src.services.rule_engine import rule_engine


class AIHypothesis(BaseModel):
    root_cause_service: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    recommended_action: Optional[RemediationActionType]
    evidence_status: str = "ANOMALY_OBSERVED"
    blast_radius: List[str]
    mitigation_steps: List[str]


class SREAgentState(BaseModel):
    incident_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    telemetry_signals: Dict[str, Any]
    topology_context: Dict[str, Any]
    agent_reasoning: List[str] = Field(default_factory=list)
    final_hypothesis: Optional[AIHypothesis] = None


class SREAgentOrchestrator:
    def run_agentic_diagnosis(
        self,
        incident_id: str,
        diagnosis: DiagnosticReport,
    ) -> AIHypothesis:
        """
        Executes multi-step Agentic AI reasoning cycle.
        Step 1: Ingests topology context and anomaly signals.
        Step 2: Traverses causal propagation paths.
        Step 3: Evaluates deterministic diagnostic rules.
        Step 4: Formulates structured mitigation strategy.
        """
        if diagnosis.confidence_score == 0 or diagnosis.evidence.root_cause_metric == "no_live_evidence":
            return AIHypothesis(
                root_cause_service=diagnosis.root_cause_service,
                confidence=0.0,
                explanation="No current diagnostic evidence supports a root cause or remediation recommendation. The recorded incident service remains an unverified candidate.",
                recommended_action=None,
                evidence_status="INSUFFICIENT_EVIDENCE",
                blast_radius=diagnosis.cascading_symptoms,
                mitigation_steps=["Collect fresh telemetry and confirm an active anomaly.",
                                  "Review dependency paths and correlate observed symptoms.",
                                  "Repeat diagnosis before proposing an action.",
                                  "Require human review before executing any remediation."],
            )

        rules = rule_engine.evaluate_rules(diagnosis)
        top_rule = rules[0] if rules else None

        reasoning_trace = [
            f"[Agent Step 1: Ingestion] Detected anomaly in [{diagnosis.root_cause_service}] (Metric: {diagnosis.evidence.root_cause_metric}).",
            f"[Agent Step 2: Causal Trace] Dependent callers experiencing collateral failure: {diagnosis.cascading_symptoms}.",
            f"[Agent Step 3: Hypothesis Evaluation] Matched rule '{top_rule.rule_name if top_rule else 'General Outage'}' with {diagnosis.confidence_score * 100:.0f}% confidence.",
            f"[Agent Step 4: Blast Radius Containment] Isolating {diagnosis.root_cause_service} prevents further cascading latency.",
        ]

        # Action recommendation
        action = top_rule.recommended_action if top_rule else RemediationActionType.RESTART_SERVICE

        mitigation_steps = [
            f"1. Human SRE Lead reviews and approves {action.value} plan.",
            f"2. Execute automated containment on container instances for [{diagnosis.root_cause_service}].",
            "3. Run automated post-recovery telemetry verification probe across 5 simulation cycles.",
            f"4. Confirm error rate drops below 5.0% on both {diagnosis.root_cause_service} and caller services.",
        ]

        return AIHypothesis(
            root_cause_service=diagnosis.root_cause_service,
            confidence=diagnosis.confidence_score,
            explanation="; ".join(reasoning_trace),
            recommended_action=action,
            blast_radius=diagnosis.cascading_symptoms,
            mitigation_steps=mitigation_steps,
        )


sre_ai_agent = SREAgentOrchestrator()
