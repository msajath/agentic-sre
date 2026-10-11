# Agentic SRE simulation platform

FastAPI, React, PostgreSQL and NetworkX demonstrate telemetry ingestion, incident detection,
dependency-aware diagnosis, human-approved simulated recovery, and a tamper-evident audit chain.
Optional local Ollama produces investigation explanations. Diagnosis and action selection use
Python heuristics. This version does **not** use LangGraph, execute Kubernetes actions, or provide
vector/semantic RAG. Runbooks use persisted lexical search. Benchmarks execute isolated simulated
cycles; their timings are harness durations, not production MTTD/MTTR.

## Local setup

Use Python 3.11+, Node 22.12+, and PostgreSQL 18. The API uses SQLAlchemy/psycopg;
Prisma owns the PostgreSQL schema, versioned migrations, generated TypeScript client, and Studio.
PostgreSQL is the only supported database. These tools share one database. The [Prisma configuration](https://www.prisma.io/docs/orm/v7/reference/prisma-config-reference)
is in `prisma.config.ts` and its models are in `prisma/schema.prisma`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
.\.venv\Scripts\python.exe scripts/local_postgres.py start
npm run db:validate
npm run db:generate
npm run db:migrate
.\.venv\Scripts\python.exe -m src.manage admin --role ADMIN
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --workers 1
```

The local database helper detects installed PostgreSQL binaries (or `PG_BIN`) and creates a
separate cluster in `data/postgres`, bound to `127.0.0.1:55432`. It creates `agentic_sre` and the
isolated `agentic_sre_test` database, with random passwords saved in the ignored `.env` file.
It leaves other PostgreSQL installations and their databases untouched. Use
`scripts/local_postgres.py stop` or `status` with the same Python interpreter to manage it.
Start it again after reboot. For an existing PostgreSQL server, set `DATABASE_URL` in `.env`
instead and run the Prisma commands; the local helper refuses to overwrite another database URL.

The account command prompts for a password without echoing it; no public default credentials are installed.
Use it again to rotate/reactivate an account, or provision an operator, lead or viewer with
`--role OPERATOR`, `--role SRE_LEAD` or `--role VIEWER`. Existing accounts that still use the old public
demo passwords are disabled at startup. Explicit `BOOTSTRAP_ADMIN_PASSWORD` can provision the
first administrator or rotate the legacy admin account. It does not overwrite a custom password.

Previously imported audit history is stored in PostgreSQL under `legacy-audit:` keys in
`platform_records`, marked unverified. `/api/v1/audit/legacy` exposes the separate archive after
authentication; the active ledger's integrity result does not claim to verify legacy history.

Run `npm run db:check` to verify the Prisma Client connection and see record counts.
Run `npm run db:studio` to inspect tables in Prisma Studio. To change the schema, edit
`prisma/schema.prisma`, run `npm run db:migrate:dev -- --name your_change` on a development
database, and regenerate the client. That development role needs permission to create a shadow
database (or an explicitly configured shadow database). Deployment uses `db:migrate`, which
does not need that permission. Keep `src/database.py` models aligned with schema changes.

The root package pins patched Prisma transitive dependencies with npm overrides. After upgrading
Prisma, review these overrides and rerun the migration, client, type and Studio checks.

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173 and sign in. Vite proxies API and authenticated WebSocket traffic to port
8000. Alternatively, `npm run build` builds a dashboard that FastAPI serves at http://localhost:8000.
To use a separate API origin, set `VITE_API_BASE_URL` at build time and configure `ALLOWED_ORIGINS` on
the backend. Tokens stay in browser memory and are validated against current database permissions.

## Incident workflow

1. Sign in as a lead or administrator and inject a simulation fault in **Chaos**. Latency magnitude
   is milliseconds; error-storm magnitude is a percentage; resource saturation raises CPU/memory
   and adds the configured latency. Faults expire automatically.
2. Detection runs in the simulator even with no dashboard connected. A persisted incident ID stays
   stable while the same service set remains degraded. Select the incident and run diagnosis.
3. Select **Propose remediation**. An operator can propose; only a lead or administrator can approve.
   All four action types model recovery by removing injected faults; no cluster resource is changed.
4. Approval records execution before recovery verification. Verification requires five fresh samples,
   recent heartbeats, healthy latency/errors and healthy affected callers. Failure leaves the incident
   open and reports `FAILED_VERIFICATION`; it never claims that a rollback occurred.

Runbook uploads and benchmark results persist in the configured database. Search citations contain actual saved
content. The evaluation page starts with unmeasured metrics; replay runs populate measured results.
Approval and safety effectiveness are not measured by that isolated harness.

## Configuration and hosting

Configuration reads environment variables, with `SRE_` aliases supported. Debug is controlled only
by `SRE_DEBUG` to avoid unrelated system `DEBUG` variables. See `.env.example`. Python and Prisma
load the project's `.env`; explicit process environment variables take precedence.

- `SECRET_KEY`: stable random signing key, at least 32 characters; mandatory with `ENVIRONMENT=production`.
  Development uses a random process key, so restarting invalidates existing tokens.
- `BOOTSTRAP_ADMIN_PASSWORD`: optional, 12 to 128 characters; configure for an empty production database.
  Otherwise provision an account using the local account command first.
- `ALLOWED_ORIGINS`: JSON array of explicit browser origins, such as `["https://sre.example.com"]`.
- `DATABASE_URL`: required `postgresql://user:password@host:port/database` URL for Python and Prisma.
  Startup rejects a missing URL or another database provider. Apply Prisma migrations before starting the API.
- `TEST_DATABASE_URL`: required for tests; use a dedicated PostgreSQL database whose name ends in `_test`.
- `POSTGRES_PASSWORD` and `DOCKER_DATABASE_URL`: credentials and internal connection URL for Docker Compose.
- `SIMULATION_ENABLED=false`: telemetry-only mode; simulated remediation is disabled.
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL`: optional local inference endpoint/model. Docker can use
  `http://host.docker.internal:11434`; a Kubernetes deployment needs a reachable configured endpoint.

Create a private `.env` with your own secrets, then run `docker compose up --build`. Compose starts
PostgreSQL, waits for readiness, applies Prisma migrations in a separate container, then starts
the API. PostgreSQL data persists in `postgres-data`; the dashboard/API image runs as a non-root user.
The Docker database is separate from the local cluster. Set a specific
image tag when deploying `k8s/deployment.yaml`; create a `sre-secrets` Secret in the `agentic-sre`
namespace containing `secret-key`, a reachable PostgreSQL `database-url` and, for first startup,
`bootstrap-admin-password`. Build/publish the Prisma init-container image using
`docker build --target database -t agentic-sre-database:0.1.0 .`; its migrations run before the API.
Update allowed browser origins for your ingress. Use `/healthz` for liveness and
`/readyz` for database/simulator readiness.

Run **one worker and one replica**: simulation state is process-local. This is a demonstration
platform, not a horizontally scalable production control plane. Kubernetes uses `Recreate` updates
to keep two simulators from running during rollout; upgrades briefly interrupt service. Back up the database before upgrades.
Incident/plan changes and their audit events commit in one transaction; storage failures return 503.
The audit verifier reads persisted records, including genesis, and detects modified or broken chains.
It cannot prove that a database administrator did not remove the chain tail or rewrite the whole
chain; external trusted checkpoints/backups are needed for that guarantee.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/test_postgres.py
.\.venv\Scripts\python.exe -m bandit -r src -ll -ii
.\.venv\Scripts\python.exe -m flake8 src scripts tests --select=F
npm run db:validate
npm run db:check
cd frontend
npm run lint
npm run build
```

All backend tests use `TEST_DATABASE_URL` from the process environment or the project's `.env`.
They drop application tables only in that dedicated test database and refuse application database names.
CI checks PostgreSQL, Prisma migrations/client, backend security, frontend lint/build,
and the Docker stack.
