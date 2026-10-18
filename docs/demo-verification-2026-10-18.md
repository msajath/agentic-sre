# Demo website and AI verification - 2026-10-18

This local verification exercised the built React site and FastAPI API against a disposable PostgreSQL database. It checks the **simulation platform** described in the [blueprint gap analysis](blueprint-gap-analysis.md); it is not evidence of a deployed Kubernetes SRE system.

| Check | Observed result |
| --- | --- |
| Backend | **106 passed** with PostgreSQL in **49m 19s** (`scripts/test_postgres.py`). After the RCA narration fix, **13 focused AI tests** and **3 end-to-end incident scenarios** passed again. |
| API collection | Newman/Postman completed **34 requests, 60 assertions, zero failures**. The runner created and dropped its own PostgreSQL test database. Ollama was intentionally pointed at an unavailable endpoint to verify deterministic fallback. |
| Frontend | `npm run lint -- --deny-warnings` and `npm run build` passed. |
| Browser demo | Headless Edge/Playwright completed **12 checks** with no JavaScript page errors. It used a separate, migrated PostgreSQL test database, which was dropped afterward. |
| Local model | Ollama reported `gemma4:latest` available; direct JSON generation and the triage and root-cause stages succeeded with the live model. Five focused AI checks passed. Malformed JSON and a missing model exercised deterministic fallback. |

The browser path covered viewer sign-up, all ten navigation sections, denial of a viewer's write attempt, sign-out, administrator login, simulated fault injection through the UI, incident detection, the investigation stream, approval, verified simulated recovery, postmortem retrieval, incident display, and a mobile-width login layout. The stream emitted completed triage, investigation, and root-cause stages, then a remediation approval checkpoint. The approval response reported `VERIFIED_SUCCESSFUL`, and the postmortem identified its mode as `simulation`. The rerun also confirmed the served favicon, readable approval text, and that the active-incident banner cleared after recovery telemetry updated.

The four named stages are sequential application stages. Triage and root-cause analysis can use Ollama for explanations; diagnosis, action choice, investigation, and remediation remain governed by deterministic application logic. The browser run disabled Ollama to test the fallback path, while the separate live-model check verified the optional Ollama path. The RCA stage now rejects a model explanation that names a service different from the telemetry-ranked candidate, even when that service is in the blast radius; a forced contradiction was rejected in a focused test. Passing these checks does not establish that four independent LLM agents can operate a real cluster.

Remaining release gaps are material: no VPS/domain or deployed staging environment was available; no real Kubernetes workload, Prometheus/log/trace backend, or Kubernetes read/write operation was exercised. The repository still lacks LangGraph-style recoverable orchestration, pgvector-backed cited RAG, and horizontally durable simulator state. The browser run is a representative local path, not a cross-browser, accessibility, load, restart/recovery, backup-restore, or production security assessment. See [the blueprint comparison](blueprint-gap-analysis.md) for the full acceptance criteria and [operations guidance](operations.md) for deployment prerequisites.
