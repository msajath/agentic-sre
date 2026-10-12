"""Local simulation evaluations, runbooks, workflow catalog, and effective settings."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.config import settings
from src.models.auth import User, UserRole
from src.services.auth_service import require_roles
from src.services.platform_service import platform_service

router = APIRouter(prefix="/api/v1", tags=["Platform"])

class RunbookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(default="Runbook", max_length=64)
    target_services: List[str] = Field(min_length=1, max_length=5)
    content: str = Field(min_length=10, max_length=100000)

    @field_validator("target_services")
    @classmethod
    def validate_services(cls, services):
        if any(service not in settings.managed_services for service in services):
            raise ValueError("Runbook targets must be managed services.")
        return services

class PlatformSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_rate_threshold: float = Field(gt=0, lt=1)
    latency_p95_threshold_ms: float = Field(gt=0, le=60000)

@router.get("/evaluations/benchmarks")
async def get_benchmarks_and_metrics():
    return platform_service.evaluations()

@router.post("/evaluations/replay/{scenario_id}")
async def replay_benchmark_scenario(scenario_id: str, user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR]))):
    try:
        return platform_service.replay(scenario_id, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/knowledge/documents")
async def list_knowledge_documents():
    return platform_service.documents()

@router.post("/knowledge/documents", status_code=201)
async def upload_runbook_document(doc: RunbookPayload, user: User = Depends(require_roles([UserRole.ADMIN, UserRole.SRE_LEAD, UserRole.OPERATOR]))):
    return platform_service.add_document(doc, user)

@router.get("/knowledge/search")
async def search_knowledge_base(query: str = Query(min_length=2, max_length=256)):
    return platform_service.search(query)

@router.get("/agents")
async def list_registered_agents():
    from src.services.ollama_adapter import ollama_adapter
    model_health = await ollama_adapter.check_health()
    narration = (f"Optional Ollama ({model_health['selected_model']})"
                 if model_health.get("can_generate") else "Deterministic Python")
    return [{"id": name.lower().replace(" ", "-"), "name": name, "role_type": "Workflow stage",
             "model": narration if name in {"Triage", "Root Cause"} else "Deterministic Python",
             "temperature": 0.1, "allowlisted_tools": tools, "status": "AVAILABLE",
             "primary_responsibility": responsibility, "total_invocations": None}
            for name, tools, responsibility in [
                ("Triage", [], "Classify simulated symptoms with optional Ollama narration."),
                ("Investigation", ["get_service_health", "query_metrics", "search_logs", "describe_topology_dependencies"], "Collect simulated telemetry and diagnostic evidence."),
                ("Root Cause", [], "Rank evidence with deterministic heuristics; optional Ollama explanation."),
                ("Remediation", ["propose_plan"], "Persist a simulated recovery plan for human approval."),
            ]]

@router.get("/services/catalog")
async def get_services_catalog():
    from src.services.topology_graph import topology_engine
    from src.services.telemetry_stream import telemetry_stream
    return [{"name": summary.service_name, "tier": topology_engine.service_metadata[summary.service_name].tier,
             "namespace": "simulation", "replicas": "Simulated", "current_image": "No live deployment",
             "p95_latency_ms": summary.p95_latency_ms, "error_rate": summary.error_rate, "status": summary.status,
             "dependencies": topology_engine.get_downstream_dependencies(summary.service_name), "endpoints": []}
            for summary in telemetry_stream.get_all_summaries()]

@router.get("/settings")
async def get_platform_settings():
    return platform_service.get_settings()

@router.post("/settings")
async def update_platform_settings(payload: PlatformSettingsPayload, user: User = Depends(require_roles([UserRole.ADMIN]))):
    return platform_service.update_settings(payload, user)
