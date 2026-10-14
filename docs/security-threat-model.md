# Security threat model (simulation release)

Reviewed 2026-10-14. This describes the current code and the controls needed before a controlled Kubernetes demo. It does not authorize production-cluster access.

## Assets and trust boundaries

Assets are signing keys, PostgreSQL credentials, user accounts, incident/audit history, runbooks, model prompts, and remediation approvals. The browser is untrusted and sends bearer tokens to FastAPI. FastAPI authenticates against PostgreSQL and keeps the simulator in process memory. Incident descriptions, logs, telemetry, and runbook text are untrusted even when submitted by an authenticated user. Optional Ollama narration crosses a separate network boundary; only configured HTTPS remote endpoints are permitted in production settings. Docker/CI images and host secrets form a separate deployment boundary.

## Threats, current controls, and release blockers

| Threat | Current control | Residual work before production-style use |
| --- | --- | --- |
| Unauthorized remediation | Role checks on API writes, persisted approval plan, rechecked approver before tool execution, no live Kubernetes write adapter. Fresh heartbeat/anomaly now required for automatic proposals and zero-evidence workflows stop. | Separate read/write service identities, namespace/environment allowlists, short-lived approval binding to an exact action and evidence version, replay protection, rollback tests. |
| Prompt injection through incidents/logs | Model inputs are delimited as untrusted JSON, common credentials are redacted, model output is schema-validated, and authorization/target selection remain deterministic. | Redact configured PII and arbitrary log secrets before storage and prompt use; test adversarial runbooks and real log adapters; record prompt/model versions. |
| Stolen or brute-forced credentials | Password hashing, JWT validation against active database users, viewer-only public signup, and role checks exist. | External identity provider/MFA, durable distributed rate limiting, session revocation and rotation, account recovery process, login monitoring. |
| Telemetry spoofing or stale signals | Typed ingestion requires an authenticated operator role; investigation and automatic proposals require recent heartbeat plus anomaly. | Service-to-service identity and signed/attributed telemetry, bounded source timestamps, independent Prometheus verification and alert deduplication. |
| Leakage through API/LLM/audit | Public Ollama health omits endpoint/model inventory; secrets are configured outside the repository; prompt inputs redact common tokens/passwords. | Central redaction policy for all stored evidence, responses and logs; private egress allowlist; retention policy; secret rotation drill. |
| Database/audit tampering | Incident/plan writes commit with audit events; hash chain detects modification of persisted entries. | External signed checkpoints and off-host backups; a database administrator can currently rewrite or truncate the entire ledger. |
| Service interruption or resource exhaustion | One worker/replica, bounded tool inputs, readiness/liveness probes, PostgreSQL backup script. | Per-user and per-incident quotas, queue/backpressure, circuit breakers, recovery-time objective and restore rehearsal, high-availability state migration. |
| Vulnerable dependencies/images | CI includes Bandit, Python/npm dependency audits and image scans. | Review new CI scan results, pin action digests, generate SBOM/provenance, patch findings and enforce release policy. |

## Safety invariant

No model output may directly execute a write. A write is a typed, allowlisted operation tied to a persisted incident, concrete target, authenticated reviewer, recorded approval, and fresh evidence. The current implementation satisfies only the simulation subset of this invariant. Keep `SIMULATION_ENABLED=true` and do not grant this image Kubernetes write credentials until the remaining controls are implemented and tested in a dedicated staging cluster.
