"""
Incident Lifecycle API Router.
Manages incident triage, state transitions, timeline forensics, and RBAC actions.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.auth import User, UserRole
from src.models.incident import (
    IncidentNoteRequest,
    IncidentRecord,
    IncidentSeverity,
    IncidentState,
    IncidentTransitionRequest,
)
from src.services.auth_service import get_current_user, require_roles
from src.services.incident_service import incident_service

router = APIRouter(prefix="/api/v1/incidents", tags=["Incident Management"])


@router.get("", response_model=List[IncidentRecord])
async def list_incidents(
    state: Optional[IncidentState] = Query(default=None),
    severity: Optional[IncidentSeverity] = Query(default=None),
    service: Optional[str] = Query(default=None),
):
    """
    Returns incident catalog with optional status and severity filtering.
    """
    return incident_service.list_incidents(state=state, severity=severity, service=service)


@router.get("/{incident_id}", response_model=IncidentRecord)
async def get_incident_by_id(incident_id: str):
    """
    Returns complete incident details including timeline of transitions and notes.
    """
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )
    return incident


@router.post("", response_model=IncidentRecord, status_code=status.HTTP_201_CREATED)
async def create_incident(
    title: str = Query(..., min_length=3, max_length=128),
    description: str = Query(..., min_length=5, max_length=512),
    severity: IncidentSeverity = Query(default=IncidentSeverity.MEDIUM),
    root_cause_service: Optional[str] = Query(default=None),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Manually initiates an incident record. Requires Operator or Lead permissions.
    """
    incident = incident_service.create_incident(
        title=title,
        description=description,
        severity=severity,
        root_cause_service=root_cause_service,
        actor=current_user.username,
        actor_role=current_user.role.value,
    )
    return incident


@router.patch("/{incident_id}/state", response_model=IncidentRecord)
async def transition_incident_state(
    incident_id: str,
    request: IncidentTransitionRequest,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Transitions incident state along the verified lifecycle state machine.
    """
    try:
        incident = incident_service.transition_state(
            incident_id=incident_id,
            target_state=request.target_state,
            reason=request.reason,
            actor=current_user.username,
            actor_role=current_user.role.value,
        )
        return incident
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{incident_id}/notes", response_model=IncidentRecord)
async def add_incident_note(
    incident_id: str,
    request: IncidentNoteRequest,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Appends a forensic triage note to an incident's immutable timeline.
    """
    try:
        incident = incident_service.add_note(
            incident_id=incident_id,
            note=request.note,
            actor=current_user.username,
            actor_role=current_user.role.value,
        )
        return incident
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
