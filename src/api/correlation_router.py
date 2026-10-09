"""
Event Correlation and Dependency Diagnosis API Router.
Exposes multi-alert clusters, causal hop DAGs, and forensic root cause evidence.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from src.models.correlation import CorrelatedIncidentGroup, DiagnosticReport
from src.services.diagnosis_engine import diagnosis_engine
from src.services.event_correlator import event_correlator
from src.services.telemetry_stream import telemetry_stream

router = APIRouter(prefix="/api/v1/correlation", tags=["Event Correlation & RCA"])


@router.get("/groups", response_model=List[CorrelatedIncidentGroup])
async def list_correlated_groups():
    """
    Returns all active correlated incident groups clustered from live telemetry.
    """
    return event_correlator.correlate_active_alerts()


@router.post("/correlate-now", response_model=List[CorrelatedIncidentGroup])
async def trigger_correlation_pass():
    """
    Forces an immediate evaluation pass of the temporal and spatial correlation engine.
    """
    return event_correlator.correlate_active_alerts()


@router.get("/diagnose-cluster", response_model=Optional[DiagnosticReport])
async def diagnose_current_cluster_state():
    """
    Produces immediate comprehensive root cause diagnostic report across all active alerts.
    """
    groups = event_correlator.correlate_active_alerts()
    if not groups:
        return None
    # Return primary incident group's diagnosis
    return groups[0].diagnosis
