"""
Event Correlation and Dependency-Aware Diagnostic Data Models.
Structures multi-alert clustering, causal DAG path traversal, and forensic evidence.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from src.models.incident import IncidentSeverity


class AlertEvent(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service_name: str
    metric_name: str
    observed_value: float
    threshold_value: float
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    message: str


class CausalHop(BaseModel):
    from_service: str
    to_service: str
    relation: str = "calls"
    impact_description: str


class ForensicEvidence(BaseModel):
    earliest_fault_timestamp: datetime
    cascade_delay_ms: float
    causal_path: List[str]
    root_cause_metric: str
    symptom_signatures: List[str]


class DiagnosticReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"RCA-{str(uuid4())[:6].upper()}")
    incident_id: Optional[str] = None
    diagnosed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    root_cause_service: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    cascading_symptoms: List[str]
    causal_chain: List[CausalHop]
    evidence: ForensicEvidence
    recommended_remediation_intent: str


class CorrelatedIncidentGroup(BaseModel):
    group_id: str = Field(default_factory=lambda: f"GRP-{str(uuid4())[:6].upper()}")
    root_cause_service: str
    affected_services: List[str]
    alert_count: int
    alerts: List[AlertEvent]
    diagnosis: DiagnosticReport
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
