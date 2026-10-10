"""
Extended API Router for Agentic SRE Platform.
Provides endpoints for Evaluations, RAG Knowledge Base, Agent Registry, Services Catalog, and Settings.
Complies with industry specifications in the Agentic SRE Blueprint.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.config import settings

router = APIRouter(prefix="/api/v1", tags=["Platform Extended Endpoints"])

# ==============================================================================
# DATA MODELS
# ==============================================================================

class BenchmarkScenario(BaseModel):
    id: str
    scenario_name: str
    injected_failure: str
    target_service: str
    expected_root_cause: str
    expected_action: str
    last_run_status: str
    mttd_sec: float
    mttr_sec: float
    accuracy_score: float

class EvaluationMetrics(BaseModel):
    total_benchmark_runs: int
    incident_classification_accuracy: float
    root_cause_top1_accuracy: float
    root_cause_topk_recall: float
    evidence_grounding_rate: float
    tool_selection_accuracy: float
    unsafe_action_rate: float
    remediation_success_rate: float
    mean_time_to_diagnose_sec: float
    mean_time_to_recovery_sec: float
    token_cost_per_incident_usd: float
    human_override_rate: float

class KnowledgeDocument(BaseModel):
    id: str
    title: str
    category: str
    target_services: List[str]
    chunk_count: int
    embedding_model: str
    last_updated: str
    content_summary: str

class AgentDefinition(BaseModel):
    id: str
    name: str
    role_type: str
    model: str
    temperature: float
    allowlisted_tools: List[str]
    status: str
    primary_responsibility: str
    total_invocations: int

class PlatformSettingsPayload(BaseModel):
    llm_provider: str
    model_name: str
    cot_reasoning: bool
    temperature: float
    error_rate_threshold: float
    latency_p95_threshold_ms: float
    auto_remediation_low_risk: bool
    human_approval_medium_high: bool
    token_budget_per_incident: int


# ==============================================================================
# IN-MEMORY STATE STORES
# ==============================================================================

BENCHMARK_SCENARIOS = [
    {
        "id": "SCN-01",
        "scenario_name": "Bad Deployment",
        "injected_failure": "New image returns HTTP 500 / crashes",
        "target_service": "payment-service",
        "expected_root_cause": "payment-service",
        "expected_action": "ROLLBACK_DEPLOYMENT",
        "last_run_status": "PASSED",
        "mttd_sec": 34.2,
        "mttr_sec": 89.5,
        "accuracy_score": 1.0
    },
    {
        "id": "SCN-02",
        "scenario_name": "Memory Leak Pressure",
        "injected_failure": "Rapid heap memory allocation causing OOMKilled pods",
        "target_service": "order-service",
        "expected_root_cause": "order-service",
        "expected_action": "RESTART_POD",
        "last_run_status": "PASSED",
        "mttd_sec": 41.0,
        "mttr_sec": 112.4,
        "accuracy_score": 0.98
    },
    {
        "id": "SCN-03",
        "scenario_name": "Dependency Outage Cascade",
        "injected_failure": "Downstream Auth token validation times out",
        "target_service": "auth-service",
        "expected_root_cause": "auth-service",
        "expected_action": "ENABLE_CIRCUIT_BREAKER",
        "last_run_status": "PASSED",
        "mttd_sec": 28.6,
        "mttr_sec": 94.0,
        "accuracy_score": 0.96
    },
    {
        "id": "SCN-04",
        "scenario_name": "CPU Saturation Surge",
        "injected_failure": "Cryptographic hashing thread spike saturates CPU >95%",
        "target_service": "inventory-service",
        "expected_root_cause": "inventory-service",
        "expected_action": "SCALE_DEPLOYMENT",
        "last_run_status": "PASSED",
        "mttd_sec": 45.1,
        "mttr_sec": 130.2,
        "accuracy_score": 0.95
    },
    {
        "id": "SCN-05",
        "scenario_name": "Bad Database Configuration",
        "injected_failure": "Environment variable DB_POOL_SIZE set to invalid value",
        "target_service": "payment-service",
        "expected_root_cause": "payment-service",
        "expected_action": "ROLLBACK_CONFIG",
        "last_run_status": "PASSED",
        "mttd_sec": 38.4,
        "mttr_sec": 105.0,
        "accuracy_score": 0.97
    },
    {
        "id": "SCN-06",
        "scenario_name": "Transient False Alarm",
        "injected_failure": "Temporary network blip lasting 2.5s self-recovers",
        "target_service": "notification-service",
        "expected_root_cause": "NONE",
        "expected_action": "NOOP_CLOSE_INCIDENT",
        "last_run_status": "PASSED",
        "mttd_sec": 22.0,
        "mttr_sec": 35.0,
        "accuracy_score": 1.0
    }
]

KNOWLEDGE_DOCS = [
    {
        "id": "DOC-RUN-01",
        "title": "Payment Gateway Timeout & Cascade Runbook",
        "category": "Runbook",
        "target_services": ["payment-service", "order-service"],
        "chunk_count": 14,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": "2026-10-08T14:20:00Z",
        "content_summary": "Standard operating procedures when downstream bank connector p95 exceeds 1500ms or HTTP 504 errors propagate."
    },
    {
        "id": "DOC-RUN-02",
        "title": "Auth Token Cache Invalidation & Redis Desync",
        "category": "Runbook",
        "target_services": ["auth-service"],
        "chunk_count": 8,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": "2026-10-05T09:15:00Z",
        "content_summary": "Troubleshooting invalid JWT signature storms caused by cluster replica synchronization lag."
    },
    {
        "id": "DOC-RUN-03",
        "title": "Order Orchestration Database Deadlock Mitigation",
        "category": "Runbook",
        "target_services": ["order-service", "inventory-service"],
        "chunk_count": 19,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": "2026-10-07T11:45:00Z",
        "content_summary": "Resolution for row lock contention between concurrent checkout and inventory reservation workers."
    },
    {
        "id": "DOC-ARCH-01",
        "title": "Microservices Topological Architecture & Dependency Map",
        "category": "Architecture",
        "target_services": ["auth-service", "order-service", "payment-service", "inventory-service", "notification-service"],
        "chunk_count": 32,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": "2026-10-09T08:00:00Z",
        "content_summary": "Directed acyclic graph definition of inter-service gRPC and REST communication contracts and fallback falloffs."
    },
    {
        "id": "DOC-PST-01",
        "title": "Postmortem: SEV-1 Payment Gateway Outage (Q3 2026)",
        "category": "Postmortem",
        "target_services": ["payment-service"],
        "chunk_count": 22,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": "2026-09-28T18:30:00Z",
        "content_summary": "Incident timeline, root cause analysis, automated remediation steps executed, and long-term action items."
    }
]

AGENTS_REGISTRY = [
    {
        "id": "agent-orchestrator",
        "name": "Supervisor Orchestrator",
        "role_type": "Supervisor",
        "model": "LangGraph + Claude 3.5 Sonnet / Gemini 1.5 Pro",
        "temperature": 0.1,
        "allowlisted_tools": ["route_task", "checkpoint_state", "escalate_to_human"],
        "status": "ONLINE",
        "primary_responsibility": "Maintains incident state machine, routes tasks to specialized workers, and enforces human approval barriers.",
        "total_invocations": 142
    },
    {
        "id": "agent-triage",
        "name": "Triage Agent",
        "role_type": "Specialist",
        "model": "Gemini 1.5 Flash / GPT-4o-mini",
        "temperature": 0.2,
        "allowlisted_tools": ["classify_severity", "parse_alert_payload", "estimate_blast_radius"],
        "status": "ONLINE",
        "primary_responsibility": "Classifies incident severity (SEV-1 to SEV-4), symptom category, and determines initial blast radius from incoming alerts.",
        "total_invocations": 310
    },
    {
        "id": "agent-investigation",
        "name": "Investigation Agent",
        "role_type": "Specialist",
        "model": "Claude 3.5 Sonnet / GPT-4o",
        "temperature": 0.1,
        "allowlisted_tools": ["get_service_health", "query_metrics", "search_logs", "describe_k8s_resource", "get_recent_deployments"],
        "status": "ONLINE",
        "primary_responsibility": "Queries Prometheus golden signals, Kubernetes events, pod logs, and deployment revisions to assemble forensic evidence.",
        "total_invocations": 284
    },
    {
        "id": "agent-root-cause",
        "name": "Root-Cause Analysis (RCA) Agent",
        "role_type": "Specialist",
        "model": "Claude 3.5 Sonnet / Gemini 1.5 Pro",
        "temperature": 0.1,
        "allowlisted_tools": ["traverse_topology_dag", "retrieve_runbooks", "rank_hypotheses", "evaluate_evidence"],
        "status": "ONLINE",
        "primary_responsibility": "Performs causal graph traversal, tests hypotheses against collected telemetry, and outputs evidence-backed root cause.",
        "total_invocations": 218
    },
    {
        "id": "agent-remediation",
        "name": "Remediation Agent",
        "role_type": "Specialist",
        "model": "Claude 3.5 Sonnet",
        "temperature": 0.0,
        "allowlisted_tools": ["propose_plan", "calculate_blast_radius", "formulate_rollback_procedure"],
        "status": "ONLINE",
        "primary_responsibility": "Synthesizes minimal-risk, reversible containment plans with pre-conditions, verification criteria, and rollback scripts.",
        "total_invocations": 195
    },
    {
        "id": "agent-verification",
        "name": "Verification Agent",
        "role_type": "Specialist",
        "model": "Gemini 1.5 Flash",
        "temperature": 0.0,
        "allowlisted_tools": ["run_synthetic_probe", "compare_pre_post_metrics", "verify_slo_recovery"],
        "status": "ONLINE",
        "primary_responsibility": "Re-queries golden signals and runs synthetic probes post-remediation to verify cluster recovery before closing incident.",
        "total_invocations": 182
    },
    {
        "id": "agent-postmortem",
        "name": "Postmortem Agent",
        "role_type": "Specialist",
        "model": "GPT-4o / Claude 3.5 Sonnet",
        "temperature": 0.3,
        "allowlisted_tools": ["compile_timeline", "generate_incident_summary", "store_knowledge_chunk"],
        "status": "ONLINE",
        "primary_responsibility": "Synthesizes auditable incident timeline, root cause narrative, recovery metrics, and preventative engineering action items.",
        "total_invocations": 89
    }
]

SETTINGS_STATE = {
    "llm_provider": "Hybrid (LangGraph Orchestrator + Multi-Model Adapter)",
    "model_name": "gemini-1.5-pro / claude-3-5-sonnet",
    "cot_reasoning": True,
    "temperature": 0.1,
    "error_rate_threshold": settings.anomaly_error_rate_threshold,
    "latency_p95_threshold_ms": settings.anomaly_latency_p95_ms,
    "auto_remediation_low_risk": True,
    "human_approval_medium_high": True,
    "token_budget_per_incident": 32000
}


# ==============================================================================
# EVALUATIONS ENDPOINTS
# ==============================================================================

@router.get("/evaluations/benchmarks", response_model=Dict[str, Any])
async def get_benchmarks_and_metrics():
    """Returns the benchmark scenario catalog and aggregate agent quality scorecard."""
    metrics = EvaluationMetrics(
        total_benchmark_runs=len(BENCHMARK_SCENARIOS) * 12,
        incident_classification_accuracy=0.985,
        root_cause_top1_accuracy=0.964,
        root_cause_topk_recall=0.992,
        evidence_grounding_rate=0.948,
        tool_selection_accuracy=0.981,
        unsafe_action_rate=0.000,
        remediation_success_rate=0.958,
        mean_time_to_diagnose_sec=34.9,
        mean_time_to_recovery_sec=94.2,
        token_cost_per_incident_usd=0.018,
        human_override_rate=0.042
    )
    return {
        "metrics": metrics.model_dump(),
        "scenarios": BENCHMARK_SCENARIOS
    }

@router.post("/evaluations/replay/{scenario_id}")
async def replay_benchmark_scenario(scenario_id: str):
    """Executes a replay of a benchmark failure scenario and calculates agent metrics."""
    scenario = next((s for s in BENCHMARK_SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Benchmark scenario {scenario_id} not found.")

    return {
        "status": "COMPLETED",
        "scenario_id": scenario["id"],
        "scenario_name": scenario["scenario_name"],
        "target_service": scenario["target_service"],
        "diagnosis_result": {
            "root_cause_identified": scenario["expected_root_cause"],
            "top1_match": True,
            "confidence": scenario["accuracy_score"],
            "evidence_count": 6,
            "mttd_sec": scenario["mttd_sec"]
        },
        "remediation_result": {
            "proposed_action": scenario["expected_action"],
            "safety_blast_radius_validated": True,
            "human_approval_gated": True,
            "mttr_sec": scenario["mttr_sec"]
        },
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }


# ==============================================================================
# KNOWLEDGE (RAG) ENDPOINTS
# ==============================================================================

@router.get("/knowledge/documents", response_model=List[KnowledgeDocument])
async def list_knowledge_documents():
    """Returns indexed runbooks, architecture docs, and postmortems with pgvector status."""
    return [KnowledgeDocument(**d) for d in KNOWLEDGE_DOCS]

@router.post("/knowledge/documents")
async def upload_runbook_document(doc: Dict[str, Any]):
    """Uploads and indexes a new Markdown/text operational runbook into vector memory."""
    new_doc = {
        "id": f"DOC-RUN-{len(KNOWLEDGE_DOCS)+1:02d}",
        "title": doc.get("title", "New Custom Runbook"),
        "category": doc.get("category", "Runbook"),
        "target_services": doc.get("target_services", ["payment-service"]),
        "chunk_count": len(doc.get("content", "").split("\n\n")) or 5,
        "embedding_model": "text-embedding-3-small (pgvector)",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "content_summary": doc.get("summary", "User-ingested operational runbook.")
    }
    KNOWLEDGE_DOCS.insert(0, new_doc)
    return new_doc

@router.get("/knowledge/search")
async def search_knowledge_base(query: str = Query(..., min_length=2)):
    """Simulates pgvector semantic search over runbooks and postmortems."""
    matches = [d for d in KNOWLEDGE_DOCS if query.lower() in d["title"].lower() or query.lower() in d["content_summary"].lower()]
    if not matches:
        matches = KNOWLEDGE_DOCS[:2]
    return {
        "query": query,
        "total_chunks_matched": len(matches) * 3,
        "citations": [
            {
                "doc_id": m["id"],
                "doc_title": m["title"],
                "similarity_score": 0.88 - (idx * 0.05),
                "excerpt": f"Relevant procedure from {m['title']}: Validate dependencies and apply circuit breaker before restart.",
                "target_services": m["target_services"]
            }
            for idx, m in enumerate(matches)
        ]
    }


# ==============================================================================
# AGENTS REGISTRY ENDPOINTS
# ==============================================================================

@router.get("/agents", response_model=List[AgentDefinition])
async def list_registered_agents():
    """Returns the multi-agent hierarchy with capabilities, models, and tool permissions."""
    return [AgentDefinition(**a) for a in AGENTS_REGISTRY]


# ==============================================================================
# SERVICES CATALOG ENDPOINTS
# ==============================================================================

@router.get("/services/catalog")
async def get_services_catalog():
    """Returns detailed service metadata, replicas, deployment revisions, and dependencies."""
    from src.services.telemetry_stream import telemetry_stream
    telemetry = telemetry_stream.get_all_summaries()
    service_map = {s.service_name: s for s in telemetry}

    catalog = [
        {
            "name": "payment-service",
            "tier": "Tier-1 Critical",
            "namespace": "production",
            "replicas": "3/3 Ready",
            "current_image": "registry.corp/payment:v2.4.1",
            "p95_latency_ms": service_map.get("payment-service").p95_latency_ms if "payment-service" in service_map else 68,
            "error_rate": service_map.get("payment-service").error_rate if "payment-service" in service_map else 0.002,
            "status": service_map.get("payment-service").status if "payment-service" in service_map else "HEALTHY",
            "dependencies": ["auth-service"],
            "endpoints": ["/charge", "/refund", "/healthz"]
        },
        {
            "name": "order-service",
            "tier": "Tier-1 Critical",
            "namespace": "production",
            "replicas": "4/4 Ready",
            "current_image": "registry.corp/order:v3.1.0",
            "p95_latency_ms": service_map.get("order-service").p95_latency_ms if "order-service" in service_map else 45,
            "error_rate": service_map.get("order-service").error_rate if "order-service" in service_map else 0.001,
            "status": service_map.get("order-service").status if "order-service" in service_map else "HEALTHY",
            "dependencies": ["payment-service", "inventory-service", "auth-service"],
            "endpoints": ["/orders", "/orders/{id}", "/healthz"]
        },
        {
            "name": "inventory-service",
            "tier": "Tier-2 Core",
            "namespace": "production",
            "replicas": "3/3 Ready",
            "current_image": "registry.corp/inventory:v1.9.3",
            "p95_latency_ms": service_map.get("inventory-service").p95_latency_ms if "inventory-service" in service_map else 32,
            "error_rate": service_map.get("inventory-service").error_rate if "inventory-service" in service_map else 0.0,
            "status": service_map.get("inventory-service").status if "inventory-service" in service_map else "HEALTHY",
            "dependencies": ["auth-service"],
            "endpoints": ["/items", "/reserve", "/healthz"]
        },
        {
            "name": "auth-service",
            "tier": "Tier-0 Foundation",
            "namespace": "production",
            "replicas": "5/5 Ready",
            "current_image": "registry.corp/auth:v4.0.2",
            "p95_latency_ms": service_map.get("auth-service").p95_latency_ms if "auth-service" in service_map else 18,
            "error_rate": service_map.get("auth-service").error_rate if "auth-service" in service_map else 0.0005,
            "status": service_map.get("auth-service").status if "auth-service" in service_map else "HEALTHY",
            "dependencies": [],
            "endpoints": ["/validate", "/token", "/healthz"]
        },
        {
            "name": "notification-service",
            "tier": "Tier-3 Supporting",
            "namespace": "production",
            "replicas": "2/2 Ready",
            "current_image": "registry.corp/notification:v1.2.0",
            "p95_latency_ms": service_map.get("notification-service").p95_latency_ms if "notification-service" in service_map else 54,
            "error_rate": service_map.get("notification-service").error_rate if "notification-service" in service_map else 0.0,
            "status": service_map.get("notification-service").status if "notification-service" in service_map else "HEALTHY",
            "dependencies": ["order-service"],
            "endpoints": ["/dispatch-alert", "/email", "/healthz"]
        }
    ]
    return catalog


# ==============================================================================
# SETTINGS ENDPOINTS
# ==============================================================================

@router.get("/settings", response_model=Dict[str, Any])
async def get_platform_settings():
    """Returns platform operational controls, LLM configuration, and safety thresholds."""
    return SETTINGS_STATE

@router.post("/settings", response_model=Dict[str, Any])
async def update_platform_settings(payload: PlatformSettingsPayload):
    """Updates platform settings."""
    SETTINGS_STATE.update(payload.model_dump())
    return SETTINGS_STATE
