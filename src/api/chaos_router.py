"""
Chaos Engineering and Failure Injection API Endpoints.
Guarantees strictly validated fault parameters to prevent malicious degradation.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from src.models.audit import AuditEventType
from src.models.chaos import ActiveFault, ChaosInjectionRequest, FaultType
from src.services.audit_service import audit_service
from src.services.chaos_controller import chaos_controller

router = APIRouter(prefix="/api/v1/chaos", tags=["Chaos Fault Injection"])


@router.post("/inject", response_model=ActiveFault, status_code=status.HTTP_201_CREATED)
async def inject_fault(request: ChaosInjectionRequest):
    """
    Injects a controlled fault into a target service.
    Enforces time-to-live expiration to prevent uncontained outages.
    """
    try:
        fault = chaos_controller.inject_fault(request)
        audit_service.record_event(
            event_type=AuditEventType.CHAOS_INJECT,
            actor=request.injected_by,
            actor_role="SRE_OPERATOR",
            target_resource=request.service_name,
            action_summary=f"Chaos fault {request.fault_type.value} injected into {request.service_name}",
            details={
                "magnitude": request.magnitude,
                "duration_sec": request.duration_sec,
                "fault_id": fault.fault_id,
            },
        )
        return fault
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/faults", response_model=List[ActiveFault])
async def list_active_faults(service_name: Optional[str] = Query(default=None)):
    """
    Lists all currently active faults across the ecosystem.
    """
    return chaos_controller.get_active_faults(service_name)


@router.delete("/faults/{service_name}", status_code=status.HTTP_200_OK)
async def clear_service_faults(
    service_name: str,
    fault_type: Optional[FaultType] = Query(default=None),
):
    """
    Manually removes injected faults from a service.
    """
    cleared = chaos_controller.remove_fault(service_name.lower(), fault_type=fault_type)
    audit_service.record_event(
        event_type=AuditEventType.CHAOS_CLEAR,
        actor="sre-operator",
        actor_role="SRE_OPERATOR",
        target_resource=service_name,
        action_summary=f"Cleared {len(cleared)} active faults on {service_name}",
        details={"cleared_fault_ids": cleared},
    )
    return {
        "status": "cleared",
        "service_name": service_name,
        "cleared_count": len(cleared),
        "cleared_fault_ids": cleared,
    }


@router.post("/reset", status_code=status.HTTP_200_OK)
async def emergency_clear_all():
    """
    Emergency kill-switch: Clears all active faults immediately.
    """
    cleared_count = chaos_controller.clear_all_faults()
    audit_service.record_event(
        event_type=AuditEventType.CHAOS_RESET,
        actor="sre-operator",
        actor_role="SRE_OPERATOR",
        target_resource="cluster-all",
        action_summary=f"Emergency reset triggered: {cleared_count} faults cleared",
        details={"cleared_count": cleared_count},
    )
    return {"status": "all_faults_cleared", "count": cleared_count}

