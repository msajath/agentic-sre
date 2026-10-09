"""
Remediation and Root Cause Rule Engine Data Models.
Enforces human-in-the-loop approval gates and post-remediation recovery verification.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class RemediationActionType(str, Enum):
    RESTART_SERVICE = "RESTART_SERVICE"
    TRIP_CIRCUIT_BREAKER = "TRIP_CIRCUIT_BREAKER"
    SCALE_REPLICAS = "SCALE_REPLICAS"
    ROLLBACK_DEPLOYMENT = "ROLLBACK_DEPLOYMENT"


class RemediationState(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    VERIFIED_SUCCESSFUL = "VERIFIED_SUCCESSFUL"
    FAILED_ROLLBACK = "FAILED_ROLLBACK"


class RuleEvaluationResult(BaseModel):
    rule_id: str
    rule_name: str
    matched: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    diagnosis_summary: str
    recommended_action: RemediationActionType
    target_service: str


class RemediationPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"REM-{str(uuid4())[:6].upper()}")
    incident_id: str
    target_service: str
    action_type: RemediationActionType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    state: RemediationState = RemediationState.PENDING_APPROVAL
    proposed_by: str = "agentic-rca-engine"
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    safety_blast_radius: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    recovery_verification_notes: Optional[str] = None


class ProposePlanRequest(BaseModel):
    incident_id: str
    target_service: str
    action_type: RemediationActionType
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=512)
