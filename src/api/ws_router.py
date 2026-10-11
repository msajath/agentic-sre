"""
WebSocket Streaming Router for Real-time Dashboard Telemetry.
Pushes sub-second telemetry, topology updates, and anomaly alerts.
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from src.config import settings
from src.services.auth_service import auth_service

from src.services.anomaly_detector import anomaly_detector
from src.services.chaos_controller import chaos_controller
from src.services.event_correlator import event_correlator
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine

router = APIRouter(tags=["WebSocket Realtime Feed"])


@router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    Continuous bi-directional or push stream for live dashboard telemetry.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        authentication = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        token = authentication.get("access_token", "")
        auth_service.resolve_token(token)
        while True:
            auth_service.resolve_token(token)
            # 1. Fetch live summaries
            summaries = [s.model_dump(mode="json") for s in telemetry_stream.get_all_summaries()]
            
            # 2. Fetch active faults
            active_faults = [f.model_dump(mode="json") for f in chaos_controller.get_active_faults()]
            
            # 3. Detect anomalies & incident candidate
            anomalies = [a.model_dump(mode="json") for a in anomaly_detector.evaluate_cluster_health()]
            incident = anomaly_detector.identify_potential_incident()
            incident_data = incident.model_dump(mode="json") if incident else None

            # 4. Correlation groups and forensic diagnosis
            corr_groups = event_correlator.correlate_active_alerts()
            groups_data = [g.model_dump(mode="json") for g in corr_groups]
            primary_diagnosis = corr_groups[0].diagnosis.model_dump(mode="json") if corr_groups else None

            # 5. Topology nodes
            topo = topology_engine.get_topology()
            edges = [{"source": e.source, "target": e.target} for e in topo.edges]

            payload = {
                "type": "TELEMETRY_SNAPSHOT",
                "services": summaries,
                "active_faults": active_faults,
                "anomalies": anomalies,
                "incident": incident_data,
                "correlated_groups": groups_data,
                "diagnosis": primary_diagnosis,
                "edges": edges,
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except (HTTPException, asyncio.TimeoutError, ValueError, AttributeError):
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        # Normal disconnect
        pass
    except Exception as e:
        print(f"[WebSocket Error] {e}")
