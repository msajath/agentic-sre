"""Generate the portable Postman collection used for isolated API smoke tests."""
import json
from pathlib import Path

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
BASE = "{{baseUrl}}"
items = []


def add(name, method, path, status=200, role=None, body=None, checks=None):
    headers = []
    if role:
        headers.append({"key": "Authorization", "value": f"Bearer {{{{{role}Token}}}}"})
    if body is not None:
        headers.append({"key": "Content-Type", "value": "application/json"})
    request = {"method": method, "header": headers, "url": BASE + path}
    if body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body)}
    tests = [f"pm.test({json.dumps(name + ' returns ' + str(status))}, () => pm.response.to.have.status({status}));"]
    tests.extend(checks or [])
    items.append({"name": name, "request": request, "event": [{"listen": "test", "script": {
        "type": "text/javascript", "exec": tests,
    }}]})


add("Health", "GET", "/healthz", checks=["pm.test('live', () => pm.expect(pm.response.json().status).to.eql('ok'));"])
add("Readiness", "GET", "/readyz", checks=["pm.test('ready', () => pm.expect(pm.response.json().status).to.eql('ready'));"])
add("Incidents require authentication", "GET", "/api/v1/incidents", 401)
add("Invalid password rejected", "POST", "/api/v1/auth/login", 401,
    body={"username": "admin", "password": "incorrect-postman-test-password"})
for role in ("admin", "operator", "viewer"):
    add(f"Login {role}", "POST", "/api/v1/auth/login", body={
        "username": f"{{{{{role}Username}}}}", "password": f"{{{{{role}Password}}}}",
    }, checks=[
        f"pm.test('{role} token and role', () => {{ const data=pm.response.json(); pm.expect(data.access_token).to.be.a('string').and.not.empty; pm.expect(data.role).to.eql('{role.upper()}'); }});",
        f"pm.environment.set('{role}Token', pm.response.json().access_token);",
    ])
add("Viewer profile", "GET", "/api/v1/auth/me", role="viewer", checks=[
    "pm.test('viewer identity', () => pm.expect(pm.response.json().role).to.eql('VIEWER'));",
])
add("AI engine status", "GET", "/api/v1/ai/status", role="operator", checks=[
    "pm.test('AI operational with provider status', () => { const data=pm.response.json(); pm.expect(data.status).to.eql('operational'); pm.expect(data.ollama.is_online).to.be.a('boolean'); });",
])
add("Ollama status", "GET", "/api/v1/ai/ollama-status", role="operator", checks=[
    "pm.test('provider status without private model inventory', () => { const data=pm.response.json(); pm.expect(data.is_online).to.be.a('boolean'); pm.expect(data.available_models).to.eql(undefined); });",
])
add("Agent catalog", "GET", "/api/v1/agents", role="viewer", checks=[
    "pm.test('four registered stages', () => pm.expect(pm.response.json()).to.have.length(4));",
])
add("Topology", "GET", "/api/v1/topology", role="viewer", checks=[
    "pm.test('service graph', () => pm.expect(pm.response.json().nodes.length).to.be.above(0));",
])
add("Telemetry services", "GET", "/api/v1/telemetry/services", role="viewer", checks=[
    "pm.test('service summaries', () => pm.expect(pm.response.json()).to.be.an('array'));",
])
add("Viewer cannot create incident", "POST", "/api/v1/incidents?title=Denied%20incident&description=Viewer%20cannot%20write", 403, role="viewer")
add("Invalid incident severity rejected", "POST", "/api/v1/incidents?title=Invalid%20incident&description=Invalid%20severity%20test&severity=NOT_A_SEVERITY", 422, role="operator")
add("Create incident", "POST", "/api/v1/incidents?title=Postman%20payment%20crash&description=Payment%20service%20crash%20affects%20orders&severity=HIGH&root_cause_service=payment-service", 201, role="operator", checks=[
    "pm.test('incident persisted', () => { const data=pm.response.json(); pm.expect(data.incident_id).to.be.a('string'); pm.expect(data.root_cause_service).to.eql('payment-service'); });",
    "pm.environment.set('incidentId', pm.response.json().incident_id);",
])
add("Analyze incident", "POST", "/api/v1/ai/analyze-incident/{{incidentId}}", role="operator", checks=[
    "pm.test('diagnosis response', () => { const data=pm.response.json(); pm.expect(data.root_cause_service).to.eql('payment-service'); pm.expect(data.explanation).to.be.a('string').and.not.empty; });",
])
add("Inject simulated fault", "POST", "/api/v1/chaos/inject", 201, role="admin", body={
    "service_name": "payment-service", "fault_type": "SERVICE_CRASH", "duration_sec": 120,
}, checks=["pm.test('fault targets payment', () => pm.expect(pm.response.json().service_name).to.eql('payment-service'));"])
add("Record fresh service heartbeat", "POST", "/api/v1/telemetry/heartbeat", role="operator", body={
    "service_name": "payment-service", "status": "HEALTHY", "active_instances": 1,
})
add("Viewer cannot start agent workflow", "GET", "/api/v1/ai/stream-investigation/{{incidentId}}", 403, role="viewer")
add("Stream all agent stages to human gate", "GET", "/api/v1/ai/stream-investigation/{{incidentId}}", role="operator", checks=[
    "const events=pm.response.text().split(/\\r?\\n/).filter(line => line.startsWith('data: ')).map(line => JSON.parse(line.slice(6)));",
    "const stages=events.filter(event => event.type==='NODE_COMPLETE').map(event => event.step.node);",
    "pm.test('triage, investigation, and RCA completed', () => pm.expect(stages).to.eql(['TRIAGE','INVESTIGATION','ROOT_CAUSE_ANALYSIS']));",
    "const checkpoint=events.find(event => event.type==='WORKFLOW_CHECKPOINT');",
    "pm.test('remediation pauses for human approval', () => { pm.expect(checkpoint).to.exist; pm.expect(checkpoint.step.node).to.eql('REMEDIATION'); pm.expect(checkpoint.state.proposed_remediation.plan_id).to.be.a('string'); });",
    "if (checkpoint) pm.environment.set('planId', checkpoint.state.proposed_remediation.plan_id);",
])
add("Investigation trace persists", "GET", "/api/v1/ai/investigations/{{incidentId}}", role="viewer", checks=[
    "pm.test('four stages saved', () => { const runs=pm.response.json(); pm.expect(runs[0].status).to.eql('PENDING_APPROVAL'); pm.expect(runs[0].state.execution_trace).to.have.length(4); });",
])
add("Plan pending approval", "GET", "/api/v1/remediation/plans/{{planId}}", role="viewer", checks=[
    "pm.test('plan pending', () => pm.expect(pm.response.json().state).to.eql('PENDING_APPROVAL'));",
])
add("Viewer cannot approve", "POST", "/api/v1/remediation/plans/{{planId}}/approve", 403, role="viewer", body={
    "reason": "Unauthorized viewer approval",
})
add("Admin approves simulated recovery", "POST", "/api/v1/remediation/plans/{{planId}}/approve", role="admin", body={
    "reason": "Validated simulated fault, evidence, and affected services",
}, checks=[
    "pm.test('approved recovery verified', () => pm.expect(pm.response.json().state).to.eql('VERIFIED_SUCCESSFUL'));",
])
add("Incident resolved", "GET", "/api/v1/incidents/{{incidentId}}", role="viewer", checks=[
    "pm.test('incident resolved', () => pm.expect(pm.response.json().state).to.eql('RESOLVED'));",
])
add("Simulation postmortem", "GET", "/api/v1/incidents/{{incidentId}}/postmortem", role="viewer", checks=[
    "pm.test('report includes evidence and verification', () => { const report=pm.response.json(); pm.expect(report.mode).to.eql('simulation'); pm.expect(report.evidence.length).to.be.above(0); pm.expect(report.recovery_verification).to.be.a('string').and.not.empty; });",
])
add("Create incident for rejection", "POST", "/api/v1/incidents?title=Postman%20rejection%20path&description=Human%20rejects%20unsafe%20recovery&root_cause_service=payment-service", 201, role="operator", checks=[
    "pm.environment.set('rejectIncidentId', pm.response.json().incident_id);",
])
add("Automatic proposal blocks without fresh evidence", "POST", "/api/v1/remediation/auto-propose/{{rejectIncidentId}}", 409, role="operator")
add("Manually propose plan for rejection", "POST", "/api/v1/remediation/propose", 201, role="operator", body={
    "incident_id": "{{rejectIncidentId}}", "target_service": "payment-service", "action_type": "RESTART_SERVICE",
}, checks=[
    "pm.test('plan proposed', () => pm.expect(pm.response.json().state).to.eql('PENDING_APPROVAL'));",
    "pm.environment.set('rejectPlanId', pm.response.json().plan_id);",
])
add("Admin rejects plan", "POST", "/api/v1/remediation/plans/{{rejectPlanId}}/reject", role="admin", body={
    "reason": "Insufficient current evidence to approve",
}, checks=["pm.test('rejection persisted', () => pm.expect(pm.response.json().state).to.eql('REJECTED'));"])
add("Audit chain verifies", "GET", "/api/v1/audit/verify", role="viewer", checks=[
    "pm.test('audit chain intact', () => pm.expect(pm.response.json().is_valid).to.eql(true));",
])
add("Legacy archive endpoint", "GET", "/api/v1/audit/legacy", role="viewer", checks=[
    "pm.test('legacy history labeled unverified', () => pm.expect(pm.response.json().verified).to.eql(false));",
])
add("Incident list includes created records", "GET", "/api/v1/incidents", role="viewer", checks=[
    "pm.test('created incidents visible', () => pm.expect(pm.response.json().length).to.be.at.least(2));",
])

collection = {"info": {"name": "Agentic SRE PostgreSQL API", "schema": SCHEMA,
                       "description": "Run against a disposable PostgreSQL database. Creates and resolves/rejects simulated incidents."},
              "item": items}
environment = {"name": "Agentic SRE isolated API test", "values": [
    {"key": "baseUrl", "value": "http://127.0.0.1:8001", "enabled": True},
    *({"key": f"{role}{part}", "value": (role if part == "Username" else ""), "enabled": True}
      for role in ("admin", "operator", "viewer") for part in ("Username", "Password")),
], "_postman_variable_scope": "environment"}
directory = Path(__file__).resolve().parent
(directory / "agentic-sre.postman_collection.json").write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
(directory / "isolated.postman_environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(items)} Postman requests.")
