"""
Agentic AI Reasoning and Multi-Agent Orchestration API Router.
Supports step-by-step live streaming traces via SSE and local Ollama llama3.1 inference.
"""

import json
import logging
from fastapi import Depends, APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.config import settings
from src.models.correlation import DiagnosticReport
from src.models.auth import User, UserRole
from src.models.incident import IncidentState
from src.services.auth_service import require_roles
from src.services.ai_agent import AIHypothesis, sre_ai_agent
from src.services.event_correlator import event_correlator
from src.services.incident_service import incident_service
from src.services.multi_agent_orchestrator import multi_agent_orchestrator
from src.services.ollama_adapter import ollama_adapter
from src.services.topology_graph import topology_engine
from src.services.agent_run_store import agent_run_store

router = APIRouter(prefix="/api/v1/ai", tags=["Agentic AI SRE Engine"])
logger = logging.getLogger(__name__)


@router.get("/investigations/{incident_id}")
async def list_investigation_runs(incident_id: str):
    """Return persisted stage traces for an incident, newest first."""
    if not incident_service.get_incident(incident_id):
        raise HTTPException(status_code=404, detail="Incident not found.")
    return agent_run_store.list_for_incident(incident_id)


@router.get("/status")
async def get_ai_engine_status():
    """
    Returns AI reasoning engine operational state and model provider status.
    """
    health = await ollama_adapter.public_health()
    return {
        "engine": "Sequential SRE investigation with optional Ollama narration",
        "provider": ("Optional local Ollama with deterministic fallback"
                     if health["is_online"] and health.get("can_generate", False)
                     else "Deterministic Synthesizer (Ollama narration unavailable)"),
        "chain_of_thought_enabled": False,
        "diagnostic_explanation_enabled": True,
        "human_in_the_loop_checkpoint": True,
        "status": "operational",
        "ollama": health
    }


@router.get("/ollama-status")
async def get_ollama_status():
    """
    Inspects status of local Ollama runtime and available models.
    """
    return await ollama_adapter.public_health()


@router.get("/stream-investigation/{incident_id}")
async def stream_multi_agent_investigation(
    incident_id: str,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR])),
):
    """
    Server-Sent Events (SSE) streaming endpoint that yields real-time agent execution traces
    from Triage -> Investigation -> RCA -> Remediation -> Human Gate.
    """
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if not incident.root_cause_service:
        raise HTTPException(status_code=400, detail="Incident has no identified root cause service.")
    if not topology_engine.is_service_registered(incident.root_cause_service):
        raise HTTPException(status_code=400, detail="Incident root cause service is not registered in topology.")
    if any(not topology_engine.is_service_registered(service) for service in incident.affected_services):
        raise HTTPException(status_code=400, detail="Incident affected service is not registered in topology.")
    if incident.state in {IncidentState.RESOLVED, IncidentState.CLOSED}:
        raise HTTPException(status_code=409, detail="Investigation requires an active incident.")
    if not settings.simulation_enabled:
        raise HTTPException(status_code=409, detail="The approval workflow is available only in simulation mode.")
    async def event_generator():
        try:
            async for chunk in multi_agent_orchestrator.stream_investigation(incident_id):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception:
            logger.exception("AI investigation failed for incident %s", incident_id)
            yield "data: " + json.dumps({"type": "WORKFLOW_ERROR", "status": "FAILED", "message": "Investigation could not complete. Review service logs before retrying."}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/analyze-incident/{incident_id}", response_model=AIHypothesis)
async def analyze_incident_with_ai(incident_id: str, current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR]))):
    """
    Executes deep multi-step Agentic AI reasoning on a given incident.
    """
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if not incident.root_cause_service:
        raise HTTPException(status_code=400, detail="Incident has no identified root cause service.")
    if not topology_engine.is_service_registered(incident.root_cause_service):
        raise HTTPException(status_code=400, detail="Incident root cause service is not registered in topology.")
    groups = event_correlator.correlate_active_alerts()
    diag = next((group.diagnosis for group in groups if group.root_cause_service == incident.root_cause_service), None)
    if diag is None:
        from src.models.correlation import ForensicEvidence
        diag = DiagnosticReport(
            incident_id=incident_id, root_cause_service=incident.root_cause_service,
            confidence_score=0.0, cascading_symptoms=incident.affected_services, causal_chain=[],
            evidence=ForensicEvidence(earliest_fault_timestamp=incident.created_at, cascade_delay_ms=0.0,
                causal_path=[incident.root_cause_service], root_cause_metric="no_live_evidence", symptom_signatures=[]),
            recommended_remediation_intent="Gather fresh evidence before approving a plan.",
        )
    return sre_ai_agent.run_agentic_diagnosis(incident_id, diag)
