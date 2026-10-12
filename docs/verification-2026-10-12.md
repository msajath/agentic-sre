# Verification on 2026-10-12

- Backend: 94 PostgreSQL-backed unit and integration tests passed, including expired-token rejection, role-change revocation, and scoped failed-login throttling.
- Postman: 30 requests, 54 assertions, zero failures against a disposable PostgreSQL database. The runner removed that database afterward.
- Prisma: schema validation, TypeScript type check, migration status, and live connection check passed. The application database is PostgreSQL at `127.0.0.1:55432` and its migration is current.
- Frontend: lint and production build passed.
- Python: `pip check` and Flake8 passed. Bandit reported no medium or high severity findings. The installed-package `pip-audit` found no known vulnerabilities after updating the local virtual environment's `pip` and `setuptools`.
- Node application dependencies: npm audits of the root and frontend packages reported zero vulnerabilities.
- Agent workflow: tests covered triage, investigation, root cause, the human approval checkpoint, missing evidence, model selection, empty model output, and timeout fallback. The API collection covered approval, rejection, and recovery.

The local Ollama server lists `gemma4:latest`; the configured `llama3.1` is not installed. The adapter selects the installed model on its first generation call. The model enables thinking by default; the narration request now disables it, caps output at 96 tokens, and rejects truncated results. Live triage and root-cause prompts both completed with Ollama narration in about 6–7 seconds on this host. Deterministic fallback remains available for model failures.

The isolated Newman 6.2.3 test runner has 19 npm advisories (7 moderate, 11 high, 1 critical) in its own dependencies. `npm audit fix --dry-run` found no compatible changes. It lives under ignored `data/postman-runner` and is not an application dependency or shipped artifact. The official Postman CLI Windows binary is about 300 MB unpacked and its install did not complete in this environment, so the collection was run with Newman. Docker stack checks were unavailable on this host.
