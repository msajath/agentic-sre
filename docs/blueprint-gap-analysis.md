# Blueprint comparison and production readiness

Source: *Agentic SRE - Multi-Agent Incident Management & Remediation, Industry-Level Project Blueprint*, 17 pages. This document treats the PDF as a product specification to compare against, not as operating instructions. Assessment date: 2026-10-14.

## Decision

**The repository is a controlled simulation, not the production-ready Kubernetes SRE product described in the blueprint.** It is suitable for a single-replica demonstration when deployed behind a TLS proxy with private PostgreSQL and an operator account. Do not connect it to a production Kubernetes cluster or describe its simulated recovery as live remediation. A Docker VPS bundle exists, but no VPS, domain, or live staging environment was provided for deployment validation.

The blueprint itself limits its project to a controlled Kubernetes demo and excludes unrestricted real-production access and destructive autonomous remediation (pages 2-3). Its "industry-level" language should not be read as approval to run automated actions on a real production cluster.

## Definition of done (blueprint page 16)

| Blueprint requirement | Status | Repository evidence and acceptance gap |
| --- | --- | --- |
| Three reproducible end-to-end incidents | Met for simulation | `tests/test_end_to_end_incidents.py` runs crash, latency and saturation through API injection, incident detection, four-stage investigation, approval, verification and postmortem. They do not exercise a real Kubernetes workload or telemetry backend. |
| Four distinct agents with explicit transitions | Partial | `src/services/multi_agent_orchestrator.py` has triage, investigation, RCA and remediation stages. They run sequentially without LangGraph checkpoint/resume semantics. Agent runs now persist stage state in `agent_runs`; approval and verification still sit outside the graph. |
| Typed tools, no arbitrary shell | Partial | `src/services/tool_gateway.py` validates named tools and exposes no shell; health/log tools read simulator state. Add real read-only Prometheus, log, trace and Kubernetes adapters, tool quotas and policy enforcement. |
| Human-approved write | Met for simulation | `src/services/remediation_engine.py` requires lead/admin approval, records it, then clears simulated faults. Live Kubernetes mutation is explicitly unavailable. |
| Source-tagged RAG | Missing | `src/services/platform_service.py` stores runbooks and returns lexical excerpts with document IDs. There are no embeddings, pgvector, retrieval tests, or RAG use inside the investigation graph. |
| Auditable agent/tool timeline | Partial | `agent_runs` now stores each completed stage and its tool-call summary; the existing audit ledger records incident and remediation actions. Tool output references, prompt/model versions and an immutable external checkpoint remain absent. |
| Objective recovery verification | Met for simulation | `src/services/remediation_engine.py` requires fresh service and caller telemetry before declaring simulated recovery. Real monitoring checks are not wired in. |
| Quantitative repeatable evaluation | Partial | Five isolated benchmark scenarios report cause/action match and harness duration. Grounding, argument validity, safety, approval and true end-to-end recovery metrics are unmeasured. |
| CI tests, security scans, containers | Partial | `.github/workflows/ci.yml` runs PostgreSQL tests, Bandit, Python and npm dependency audits, frontend lint/build, Trivy image scans and Docker smoke; all passed in [the corrected CI run](https://github.com/msajath/agentic-sre/actions/runs/38544986829). Add a full staging scenario gate. |
| Kubernetes probes | Partial | `k8s/deployment.yaml` has startup/liveness/readiness probes and a migration init container. Deployed kind/staging verification is outstanding. The current manifest deploys the simulator. |
| Secrets outside repo and redaction | Partial | Deployment reads Secret/env values; the prompt boundary now redacts common credential patterns. Add configured PII rules, redaction tests across logs/audit exports, key rotation and a live secret manager path. |
| Complete architecture/API/security/evaluation/deployment docs | Partial | `README.md`, `docs/operations.md`, OpenAPI and verification notes cover the simulator. A threat model, real adapter contracts, SLOs, failure modes and deployment evidence are missing. |
| Demo from injection to postmortem | Met for simulation | `tests/test_end_to_end_incidents.py` traverses the full API path for three synthetic incidents; a resolved incident has a factual postmortem endpoint and UI. No real demo cluster has been exercised. |

## Architecture delta

The PDF recommends React/TypeScript, FastAPI with LangGraph, PostgreSQL/pgvector, Redis, Prometheus/Grafana/Loki/OpenTelemetry, Kubernetes demo workloads, and pluggable LLMs (pages 4-7). The repository uses React/JavaScript, FastAPI, PostgreSQL with Prisma migrations, process-local simulated telemetry, heuristic diagnosis, optional Ollama narration, and Docker/Kubernetes deployment manifests. There is no Redis, pgvector, LangGraph, Prometheus/Loki/OTel integration, registered Kubernetes environments, deployment history, trace lookup, or live tool gateway. This difference is functional, not a naming issue: adding dependencies without operating data sources would not satisfy the blueprint.

The active production-mode Compose bundle still defaults to `SIMULATION_ENABLED=true`. "Production" there controls secret/configuration checks and hosting settings, not the truthfulness or availability guarantees of the incident engine. One worker and one replica are required because telemetry and chaos state are process-local. That imposes downtime during `Recreate` upgrades and loses transient state on restart.

## Release gates before claiming the blueprint target

1. **Controlled environment:** run a demo service in kind or a dedicated staging cluster, register its namespace/services, and provision a read-only service account. Verify alert injection and query real Prometheus metrics, logs, traces, deployment metadata, and Kubernetes state with source IDs and time bounds. Keep the Docker VPS path for hosting the control plane if desired; it does not replace the Kubernetes demo target.
2. **Durable workflow:** move alert deduplication and current incident state to PostgreSQL/Redis, add a recoverable graph/checkpoint mechanism, complete verification and postmortem nodes, persist individual tool inputs/results with bounded redacted evidence, and exercise restart/resume behavior.
3. **Knowledge and evaluation:** add versioned runbook ingestion with embeddings/pgvector and cited retrieval inside RCA; create at least three full workflow scenarios and measure grounding, tool validity, unsafe execution, approval, root-cause accuracy and verified recovery. Report unsupported metrics as unmeasured.
4. **Security and operations:** enforce per-environment tool and namespace allowlists, separate read/write identities, quotas and circuit breakers, broader prompt/evidence redaction, restricted egress, backup restore rehearsals, SLO alerts, key rotation and incident response. Verify dependency/container scans and test the deployment on the actual staging host/cluster.

Until these gates pass, release notes, UI, and demos must continue to label telemetry, logs, recovery and evaluation as simulated.
