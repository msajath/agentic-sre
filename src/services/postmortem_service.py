"""Generate a factual simulation postmortem from persisted incident records."""

from src.models.incident import IncidentState
from src.services.agent_run_store import agent_run_store
from src.services.incident_service import incident_service
from src.services.remediation_engine import remediation_engine


class PostmortemService:
    def generate(self, incident_id: str) -> dict:
        incident = incident_service.get_incident(incident_id)
        if incident is None:
            raise KeyError("Incident not found.")
        if incident.state not in {IncidentState.RESOLVED, IncidentState.CLOSED}:
            raise ValueError("Postmortem is available after verified resolution.")

        runs = agent_run_store.list_for_incident(incident_id, limit=1)
        state = runs[0]["state"] if runs else {}
        plans = [plan for plan in remediation_engine.list_plans() if plan.incident_id == incident_id]
        verified = next((plan for plan in reversed(plans) if plan.state.value == "VERIFIED_SUCCESSFUL"), None)
        return {
            "incident_id": incident_id,
            "title": incident.title,
            "severity": incident.severity.value,
            "state": incident.state.value,
            "mode": "simulation",
            "created_at": incident.created_at.isoformat(),
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "affected_services": incident.affected_services,
            "impact_note": "User and business impact were not measured by this simulator.",
            "root_cause_candidate": state.get("root_cause_service") or incident.root_cause_service,
            "root_cause_confidence": state.get("confidence_score"),
            "causality_note": "The root cause is a heuristic candidate, not independently proven causation.",
            "timeline": [event.model_dump(mode="json") for event in incident.timeline],
            "agent_trace": state.get("execution_trace", []),
            "evidence": state.get("evidence_bundle", []),
            "remediation_plans": [
                {"plan_id": plan.plan_id, "action_type": plan.action_type.value,
                 "target_service": plan.target_service, "state": plan.state.value,
                 "proposed_by": plan.proposed_by, "approved_by": plan.approved_by,
                 "verification_notes": plan.recovery_verification_notes}
                for plan in plans
            ],
            "recovery_verification": verified.recovery_verification_notes if verified else None,
        }


postmortem_service = PostmortemService()
