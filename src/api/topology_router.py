"""
Topology Mapping and Dependency Tracing API Router.
Visualizes service relationship graph and computes blast radiuses.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

from src.models.topology import ServiceTopology
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine

router = APIRouter(prefix="/api/v1/topology", tags=["Service Topology"])


@router.get("", response_model=ServiceTopology)
async def get_service_topology():
    """
    Returns complete static service graph topology.
    """
    return topology_engine.get_topology()


@router.get("/live-graph")
async def get_live_annotated_topology() -> Dict[str, Any]:
    """
    Returns topology graph annotated with live real-time health badges and active faults.
    """
    topology = topology_engine.get_topology()
    summaries = {s.service_name: s for s in telemetry_stream.get_all_summaries()}

    annotated_nodes = []
    for node in topology.nodes:
        summary = summaries.get(node.id)
        annotated_nodes.append({
            "id": node.id,
            "name": node.name,
            "tier": node.tier,
            "description": node.description,
            "status": summary.status.value if summary else "HEALTHY",
            "error_rate": summary.error_rate if summary else 0.0,
            "p95_latency_ms": summary.p95_latency_ms if summary else 0.0,
            "cpu_usage_pct": summary.cpu_usage_pct if summary else 0.0,
            "active_faults": summary.active_faults if summary else [],
            "icon": node.icon,
        })

    return {
        "nodes": annotated_nodes,
        "edges": [{"source": e.source, "target": e.target, "relation": e.relation} for e in topology.edges],
    }


@router.get("/blast-radius/{service_name}")
async def get_service_blast_radius(service_name: str):
    """
    Computes all upstream services that depend on this service.
    """
    svc = service_name.lower()
    if not topology_engine.is_service_registered(svc):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found.",
        )

    affected = topology_engine.get_affected_dependents(svc)
    downstream = topology_engine.get_downstream_dependencies(svc)

    return {
        "service_name": svc,
        "upstream_affected_callers": affected,
        "downstream_dependencies": downstream,
        "blast_radius_size": len(affected),
    }
