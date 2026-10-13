CREATE TABLE agent_runs (
    run_id VARCHAR(32) NOT NULL PRIMARY KEY,
    incident_id VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    state TEXT NOT NULL,
    started_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_agent_runs_incident_started ON agent_runs (incident_id, started_at);
