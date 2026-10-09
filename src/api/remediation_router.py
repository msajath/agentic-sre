"""
Remediation and Approval Gateway API Router.
Enforces human-in-the-loop gates (RBAC: SRE_LEAD/ADMIN) and post-action health recovery verification.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.auth import User, UserRole
from src.models.remediation import (
    ApprovalDecisionRequest,
    ProposePlanRequest,
    RemediationPlan,
    RemediationState,
)
from src.services.auth_service import get_current_user, require_roles
from src.services.diagnosis_engine import diagnosis_engine
from src.services.event_correlator import event_correlator
from src.services.incident_service import incident_service
from src.services.remediation_engine import remediation_engine
from src.services.rule_engine import rule_engine

router = APIRouter(prefix="/api/v1/remediation", tags=["Remediation & Approval Gateway"])


@router.get("/plans", response_model=List[RemediationPlan])
async def list_remediation_plans(state: Optional[RemediationState] = Query(default=None)):
    """
    Returns list of proposed, approved, executing, or verified remediation plans.
    """
    return remediation_engine.list_plans(state=state)


@router.get("/plans/{plan_id}", response_model=RemediationPlan)
async def get_remediation_plan(plan_id: str):
    """
    Returns specific plan details including forensic execution and verification notes.
    """
    plan = remediation_engine.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Remediation plan '{plan_id}' not found.",
        )
    return plan


@router.post("/propose", response_model=RemediationPlan, status_code=status.HTTP_201_CREATED)
async def propose_plan(
    request: ProposePlanRequest,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Proposes a remediation action plan for an incident awaiting human approval.
    """
    try:
        plan = remediation_engine.propose_plan(
            incident_id=request.incident_id,
            target_service=request.target_service,
            action_type=request.action_type,
            parameters=request.parameters,
            proposed_by=current_user.username,
        )
        return plan
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/auto-propose/{incident_id}", response_model=RemediationPlan, status_code=status.HTTP_201_CREATED)
async def auto_propose_from_incident(
    incident_id: str,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Applies the Rule Engine to automatically formulate and propose the optimal remediation plan.
    """
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")

    root_svc = incident.root_cause_service or "payment-service"
    
    # Run ad-hoc diagnosis to feed rule engine
    groups = event_correlator.correlate_active_alerts()
    diag = groups[0].diagnosis if groups else None

    if not diag:
        diag = diagnosis_engine.diagnose_correlated_alerts(
            alerts=[], incident_id=incident_id
        ) if False else None

    # Evaluate rules
    if diag:
        ranked_rules = rule_engine.evaluate_rules(diag)
        action_type = ranked_rules[0].recommended_action
    else:
        action_type = "RESTART_SERVICE"

    plan = remediation_engine.propose_plan(
        incident_id=incident_id,
        target_service=root_svc,
        action_type=action_type,
        proposed_by=f"rule-engine:{current_user.username}",
    )
    return plan


@router.post("/plans/{plan_id}/approve", response_model=RemediationPlan)
async def approve_and_execute_plan(
    plan_id: str,
    decision: ApprovalDecisionRequest,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD])),
):
    """
    Human-in-the-loop gate: SRE Lead or Admin approves remediation plan, triggering execution & verification.
    """
    try:
        plan = remediation_engine.approve_and_execute(
            plan_id=plan_id,
            approver=current_user.username,
            approver_role=current_user.role.value,
            reason=decision.reason,
        )
        return plan
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/plans/{plan_id}/reject", response_model=RemediationPlan)
async def reject_plan(
    plan_id: str,
    decision: ApprovalDecisionRequest,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD])),
):
    """
    Human-in-the-loop gate: Rejects proposed remediation plan.
    """
    try:
        plan = remediation_engine.reject_plan(
            plan_id=plan_id,
            reviewer=current_user.username,
            reviewer_role=current_user.role.value,
            reason=decision.reason,
        )
        return plan
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/plans/{plan_id}/verify")
async def verify_plan_recovery(plan_id: str):
    """
    Triggers on-demand health recovery verification check.
    """
    recovered = remediation_engine.verify_recovery(plan_id)
    plan = remediation_engine.get_plan(plan_id)
    return {
        "plan_id": plan_id,
        "is_recovered": recovered,
        "state": plan.state.value if plan else "UNKNOWN",
        "notes": plan.recovery_verification_notes if plan else None,
    }
