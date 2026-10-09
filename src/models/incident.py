"""
Incident and Anomaly data structures with complete lifecycle state machine.
Enforces strict transitions and captures auditable triage timelines.
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
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentTimelineEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = "system"
    action: str
    from_state: Optional[IncidentState] = None
    to_state: Optional[IncidentState] = None
    note: str = ""


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
    assigned_to: Optional[str] = None
    timeline: List[IncidentTimelineEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


class IncidentTransitionRequest(BaseModel):
    target_state: IncidentState
    reason: str = Field(..., min_length=3, max_length=512)


class IncidentNoteRequest(BaseModel):
    note: str = Field(..., min_length=2, max_length=1024)
