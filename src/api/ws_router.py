"""
WebSocket Streaming Router for Real-time Dashboard Telemetry.
Pushes sub-second telemetry, topology updates, and anomaly alerts.
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.services.anomaly_detector import anomaly_detector
from src.services.chaos_controller import chaos_controller
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine

router = APIRouter(tags=["WebSocket Realtime Feed"])


@router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    Continuous bi-directional or push stream for live dashboard telemetry.
    """
    await websocket.accept()
    try:
        while True:
            # 1. Fetch live summaries
            summaries = [s.model_dump(mode="json") for s in telemetry_stream.get_all_summaries()]
            
            # 2. Fetch active faults
            active_faults = [f.model_dump(mode="json") for f in chaos_controller.get_active_faults()]
            
            # 3. Detect anomalies & incident candidate
            anomalies = [a.model_dump(mode="json") for a in anomaly_detector.evaluate_cluster_health()]
            incident = anomaly_detector.identify_potential_incident()
            incident_data = incident.model_dump(mode="json") if incident else None

            # 4. Topology nodes
            topo = topology_engine.get_topology()
            edges = [{"source": e.source, "target": e.target} for e in topo.edges]

            payload = {
                "type": "TELEMETRY_SNAPSHOT",
                "services": summaries,
                "active_faults": active_faults,
                "anomalies": anomalies,
                "incident": incident_data,
                "edges": edges,
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        # Normal disconnect
        pass
    except Exception as e:
        print(f"[WebSocket Error] {e}")
