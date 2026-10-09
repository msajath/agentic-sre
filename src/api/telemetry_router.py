"""
Telemetry and Ingestion API Endpoints.
Ensures zero SQL injection, strict payload validation, and bounded responses.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from src.models.incident import AnomalyReport, IncidentRecord
from src.models.telemetry import HeartbeatPayload, ServiceMetricsSummary, TelemetryPoint
from src.services.anomaly_detector import anomaly_detector
from src.services.telemetry_stream import telemetry_stream
from src.config import settings

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry Ingestion"])


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def ingest_telemetry_event(point: TelemetryPoint):
    """
    Ingests a single high-resolution telemetry point from any cluster microservice.
    """
    telemetry_stream.record_telemetry(point)
    return {"status": "accepted", "service_name": point.service_name}


@router.post("/heartbeat", status_code=status.HTTP_200_OK)
async def ingest_heartbeat(payload: HeartbeatPayload):
    """
    Ingests an authenticated service heartbeat.
    """
    telemetry_stream.record_heartbeat(payload)
    return {"status": "healthy", "service_name": payload.service_name}


@router.get("/services", response_model=List[ServiceMetricsSummary])
async def list_service_metrics():
    """
    Returns live aggregated metrics summaries for all monitored services.
    """
    return telemetry_stream.get_all_summaries()


@router.get("/services/{service_name}", response_model=ServiceMetricsSummary)
async def get_service_metrics(service_name: str):
    """
    Returns specific metric statistics for a single service.
    """
    if service_name.lower() not in settings.managed_services:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' is not registered in platform catalog.",
        )
    return telemetry_stream.get_service_summary(service_name.lower())


@router.get("/services/{service_name}/events", response_model=List[TelemetryPoint])
async def get_service_recent_events(
    service_name: str,
    limit: int = Query(default=30, ge=1, le=100),
):
    """
    Returns raw recent telemetry events for diagnostics.
    """
    return telemetry_stream.get_recent_points(service_name.lower(), limit=limit)


@router.get("/anomalies", response_model=List[AnomalyReport])
async def get_active_anomalies():
    """
    Returns current active anomalies detected across the cluster.
    """
    return anomaly_detector.evaluate_cluster_health()


@router.get("/incident-candidate", response_model=Optional[IncidentRecord])
async def get_incident_candidate():
    """
    Returns correlated incident candidate based on current cluster health.
    """
    return anomaly_detector.identify_potential_incident()
