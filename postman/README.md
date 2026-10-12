# API workflow checks

Import `agentic-sre.postman_collection.json` and `isolated.postman_environment.json` into Postman.
The collection runs its 30 requests in order and checks authentication, role permissions,
agent investigation stages, the human approval gate, recovery, rejection, and audit integrity.
Set the six account variables in the environment before a manual run. Use a disposable
PostgreSQL database because this collection creates incidents and plans.

On this workspace, run `python scripts/run_postman.py` from the project root with the project's
virtual environment Python. The runner creates a new local PostgreSQL database, provisions three
temporary accounts, serves the API at `127.0.0.1:8001`, runs the collection with Newman 6.2.3,
and removes the temporary database. It writes a sanitized result to
`data/postman-summary.json`. The runner installs Newman into the ignored
`data/postman-runner` directory on first use.
