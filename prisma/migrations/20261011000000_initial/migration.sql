-- Initial PostgreSQL schema shared by Prisma and the FastAPI models.

CREATE TABLE audit_ledger (
	log_id VARCHAR(64) NOT NULL, 
	timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	event_type VARCHAR(64) NOT NULL, 
	actor VARCHAR(64) NOT NULL, 
	actor_role VARCHAR(32) NOT NULL, 
	target_resource VARCHAR(128) NOT NULL, 
	action_summary VARCHAR(256) NOT NULL, 
	details TEXT DEFAULT '{}', 
	prev_hash VARCHAR(64) NOT NULL, 
	entry_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (log_id)
);

CREATE INDEX ix_audit_ledger_entry_hash ON audit_ledger (entry_hash);

CREATE INDEX ix_audit_ledger_event_type ON audit_ledger (event_type);

CREATE INDEX ix_audit_ledger_log_id ON audit_ledger (log_id);

CREATE INDEX ix_audit_ledger_timestamp ON audit_ledger (timestamp);

CREATE TABLE incidents (
	incident_id VARCHAR(32) NOT NULL, 
	title VARCHAR(256) NOT NULL, 
	description TEXT NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	severity VARCHAR(32) NOT NULL, 
	root_cause_service VARCHAR(64), 
	affected_services TEXT DEFAULT '[]', 
	timeline TEXT DEFAULT '[]', 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (incident_id)
);

CREATE INDEX ix_incidents_incident_id ON incidents (incident_id);

CREATE INDEX ix_incidents_severity ON incidents (severity);

CREATE INDEX ix_incidents_state ON incidents (state);

CREATE TABLE platform_records (
	key VARCHAR(128) NOT NULL, 
	payload TEXT NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE remediation_plans (
	plan_id VARCHAR(32) NOT NULL, 
	incident_id VARCHAR(32) NOT NULL, 
	target_service VARCHAR(64) NOT NULL, 
	action_type VARCHAR(64) NOT NULL, 
	parameters TEXT DEFAULT '{}', 
	state VARCHAR(32) NOT NULL, 
	proposed_by VARCHAR(64) NOT NULL, 
	approved_by VARCHAR(64), 
	rejected_by VARCHAR(64), 
	rejection_reason TEXT, 
	safety_blast_radius TEXT DEFAULT '[]', 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	executed_at TIMESTAMP WITHOUT TIME ZONE, 
	verified_at TIMESTAMP WITHOUT TIME ZONE, 
	recovery_verification_notes TEXT, 
	PRIMARY KEY (plan_id)
);

CREATE INDEX ix_remediation_plans_incident_id ON remediation_plans (incident_id);

CREATE INDEX ix_remediation_plans_plan_id ON remediation_plans (plan_id);

CREATE INDEX ix_remediation_plans_state ON remediation_plans (state);

CREATE TABLE users (
	username VARCHAR(32) NOT NULL, 
	email VARCHAR(128) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	hashed_password VARCHAR(256) NOT NULL, 
	salt VARCHAR(64) NOT NULL, 
	full_name VARCHAR(128) NOT NULL, 
	is_active BOOLEAN DEFAULT true, 
	PRIMARY KEY (username), 
	UNIQUE (email)
);

CREATE INDEX ix_users_username ON users (username);
