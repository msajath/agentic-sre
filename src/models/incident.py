"""
Incident and Anomaly data structures.
Tracks lifecycle state transitions with full forensic context.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    CORRELATED = "CORRELATED"
    DIAGNOSING = "DIAGNOSING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    RESOLVED = "RESOLVED"


class AnomalyReport(BaseModel):
    anomaly_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    service_name: str
    metric_type: str
    observed_value: float
    threshold_value: float
    description: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: IncidentSeverity = IncidentSeverity.MEDIUM


class IncidentRecord(BaseModel):
    incident_id: str = Field(default_factory=lambda: f"INC-{str(uuid4())[:6].upper()}")
    title: str
    description: str
    state: IncidentState = IncidentState.DETECTED
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    root_cause_service: Optional[str] = None
    affected_services: List[str] = Field(default_factory=list)
    anomalies: List[AnomalyReport] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
