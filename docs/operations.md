# Operations runbook

This project is a single-replica SRE **simulation**. The API and dashboard share one image;
Prisma migrations run from a separate image against PostgreSQL. It does not execute Kubernetes
remediation. Keep the API at one worker and one replica because simulation state is process-local.

## Release and deploy

CI runs Python security/import checks, PostgreSQL-backed tests, Prisma validation and migration
checks, frontend lint/build, and a Docker Compose smoke test. A `v*` Git tag triggers those same
gates and, after they pass, publishes `ghcr.io/<owner>/<repo>:<tag>` and
`ghcr.io/<owner>/<repo>-database:<tag>` with GitHub Actions' package token. No image is published
from a failed pipeline. Confirm the image digests in the workflow output before deployment.

For a Docker host, provide a private `.env` with `SECRET_KEY`, `POSTGRES_PASSWORD`,
`DOCKER_DATABASE_URL`, and an initial `BOOTSTRAP_ADMIN_PASSWORD` (or provision the admin account
beforehand). Set `ALLOWED_ORIGINS` to the actual browser origin. Set `DOCKER_OLLAMA_BASE_URL` to a
trusted HTTPS inference proxy if model narration is needed. The default example hostname is only
a placeholder; the app falls back to deterministic narration if it cannot connect. Run
`docker compose config --quiet`, then `docker compose up -d --build`. The API binds to the host's
loopback interface on `SRE_HOST_PORT` (8000 by default); put a TLS reverse proxy in front of it for remote access. Check
`/readyz`, `/login`, and `/signup`. Do not publish the PostgreSQL service port.

For Kubernetes, replace both image references in `k8s/deployment.yaml` with the tested release
image digests. Create the `agentic-sre` namespace and a `sre-secrets` Secret containing
`database-url` and `secret-key`; add `bootstrap-admin-password` only for initial provisioning.
Use a reachable PostgreSQL URL and a secret manager or your cluster's approved secret delivery.
Change `ALLOWED_ORIGINS` and `OLLAMA_BASE_URL` in the ConfigMap to actual HTTPS endpoints.
Then apply the manifest. The Prisma init container must finish before the API starts. Recheck
the deployment rollout and `/readyz` through your ingress. The manifest uses `Recreate` to avoid
overlapping simulators, so upgrades briefly interrupt the API.

Never run `prisma migrate dev` against production. The migration image runs `prisma migrate
deploy`, which applies versioned migrations. Review the SQL and take a verified backup before
deploying a schema-changing release. A failed migration must be resolved before starting a new
API image; do not force the API to run against a partial schema.

## Backup and recovery

Back up the PostgreSQL database before upgrades and on a schedule appropriate to your recovery
objective. From a trusted host with PostgreSQL client tools and `DATABASE_URL` in its environment:

```bash
pg_dump --format=custom --file=agentic-sre.backup "$DATABASE_URL"
pg_restore --list agentic-sre.backup > /dev/null
```

Store the backup encrypted with restricted access and retention. A successful `--list` only checks
archive readability; regularly restore into a **separate empty database** and run the API's
`/readyz` check there to verify recovery. For a restore rehearsal, point `RESTORE_DATABASE_URL`
at that isolated database and use `pg_restore --no-owner --dbname="$RESTORE_DATABASE_URL"
agentic-sre.backup`. Stop writers and follow your database provider's recovery process before
restoring a real deployment. The application audit chain lives in the same database; retain
off-database backups/checkpoints if protection against database-administrator tampering matters.

Rolling back an application image is possible only if its older code supports the migrated schema.
Prisma migrations here are forward-only. If a schema change is incompatible, restore the pre-upgrade
backup to an isolated database first, validate it, and plan a controlled cutover. A restore replaces
all writes made after the backup.

## Observe and respond

`/healthz` is the liveness check and `/readyz` checks PostgreSQL and the simulator. A failed
readiness check means the service should not receive traffic. Inspect API container logs,
PostgreSQL health, and the migration container/job before restarting. If the optional Ollama
endpoint is unavailable, investigation narration falls back to deterministic text; recovery
approval still requires a human. Track database backups, disk space, container restarts, and
readiness failures with the hosting platform. Keep signing keys and database credentials out of
images, Git, CI logs, and dashboard responses. Rotate credentials in the secret store and restart
the single replica in a controlled maintenance window.
