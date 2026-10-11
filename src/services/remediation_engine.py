"""Approval-gated simulated actions with durable state and evidence-based verification."""
from datetime import datetime, timezone
import json
import threading
from src.config import settings
from src.database import IncidentModel, RemediationPlanModel, SessionLocal
from src.models.audit import AuditEventType
from src.models.incident import IncidentState, IncidentTimelineEvent
from src.models.remediation import RemediationActionType, RemediationPlan, RemediationState
from src.services.audit_service import audit_service
from src.services.auth_service import auth_service
from src.services.chaos_controller import chaos_controller
from src.services.incident_service import incident_service
from src.services.simulation_engine import simulation_engine
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine

class RemediationEngine:
    def __init__(self):
        self._lock = threading.RLock()

    def initialize(self):
        # Never report an interrupted action as successful or execute it again automatically.
        for plan in self.list_plans():
            if plan.state in {RemediationState.APPROVED, RemediationState.EXECUTING}:
                plan.state = RemediationState.EXECUTION_FAILED
                plan.recovery_verification_notes = "Execution interrupted; review and propose a new plan."
                self._persist(plan, AuditEventType.REMEDIATION_EXECUTE, "system", "SYSTEM", plan.recovery_verification_notes)

    @staticmethod
    def _from_row(row):
        data = {column.name: getattr(row, column.name) for column in RemediationPlanModel.__table__.columns}
        for key in ("parameters", "safety_blast_radius"):
            data[key] = json.loads(data[key])
        for key in ("created_at", "executed_at", "verified_at"):
            if data[key] and data[key].tzinfo is None:
                data[key] = data[key].replace(tzinfo=timezone.utc)
        return RemediationPlan(**data)

    @staticmethod
    def _save(session, plan):
        data = plan.model_dump(mode="python")
        data["action_type"], data["state"] = plan.action_type.value, plan.state.value
        data["parameters"] = json.dumps(plan.parameters)
        data["safety_blast_radius"] = json.dumps(plan.safety_blast_radius)
        session.merge(RemediationPlanModel(**data))
        session.flush()

    def _persist(self, plan, event_type, actor, actor_role, summary):
        with SessionLocal.begin() as session:
            self._save(session, plan)
            audit_service.record_event(event_type, actor, actor_role, plan.target_service, summary,
                                       {"plan_id": plan.plan_id, "simulation": True}, session)

    @staticmethod
    def _reviewer(username, role):
        user = auth_service.get_user_by_username(username)
        if not user or not user.is_active or user.role.value != role or role not in {"ADMIN", "SRE_LEAD"}:
            raise PermissionError("Approval requires an active administrator or SRE lead.")

    def propose_plan(self, incident_id, target_service, action_type, parameters=None, proposed_by="agentic-rca-engine"):
        action_type = RemediationActionType(action_type)
        if not settings.simulation_enabled:
            raise ValueError("Remediation execution is available only in simulation mode.")
        if not topology_engine.is_service_registered(target_service):
            raise ValueError(f"Service '{target_service}' is not recognized in topology.")
        incident = incident_service.get_incident(incident_id)
        if not incident or incident.state in {IncidentState.RESOLVED, IncidentState.CLOSED}:
            raise ValueError("Remediation requires an active, persisted incident.")
        with self._lock:
            for existing in self.list_plans(RemediationState.PENDING_APPROVAL):
                if (existing.incident_id, existing.target_service, existing.action_type) == (incident_id, target_service, action_type):
                    return existing
            plan = RemediationPlan(incident_id=incident_id, target_service=target_service, action_type=action_type,
                                   parameters=parameters or {}, proposed_by=proposed_by,
                                   safety_blast_radius=topology_engine.get_affected_dependents(target_service))
            self._persist(plan, AuditEventType.REMEDIATION_REQUEST, proposed_by, "AGENTIC_ENGINE",
                          f"Simulated plan {plan.plan_id} proposed: {action_type.value} on {target_service}")
            return plan

    def approve_and_execute(self, plan_id, approver, approver_role, reason):
        self._reviewer(approver, approver_role)
        with self._lock:
            plan = self.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Remediation plan '{plan_id}' does not exist.")
            if plan.state != RemediationState.PENDING_APPROVAL:
                raise ValueError("Only pending plans can be approved.")
            incident = incident_service.get_incident(plan.incident_id)
            if not incident or incident.state in {IncidentState.RESOLVED, IncidentState.CLOSED}:
                raise ValueError("The incident is no longer active.")
            if not settings.simulation_enabled:
                raise ValueError("Live Kubernetes execution is not implemented.")
            plan.state, plan.approved_by = RemediationState.APPROVED, approver
            self._persist(plan, AuditEventType.REMEDIATION_APPROVAL, approver, approver_role, f"Approved {plan_id}: {reason}")
            plan.state = RemediationState.EXECUTING
            plan.executed_at = datetime.now(timezone.utc)
            self._persist(plan, AuditEventType.REMEDIATION_EXECUTE, approver, approver_role, f"Starting simulated {plan.action_type.value}")
            if incident.state in {IncidentState.DETECTED, IncidentState.ACKNOWLEDGED, IncidentState.PENDING_APPROVAL}:
                incident = incident_service.transition_state(incident.incident_id, IncidentState.INVESTIGATING,
                                                            "Approved remediation", approver, approver_role)
            if incident.state != IncidentState.REMEDIATING:
                incident_service.transition_state(incident.incident_id, IncidentState.REMEDIATING,
                                                  "Executing approved simulation plan", approver, approver_role)
            try:
                self._execute_action(plan)
            except Exception:
                plan.state = RemediationState.EXECUTION_FAILED
                plan.recovery_verification_notes = "Simulated execution failed; inspect logs before retrying."
                self._persist(plan, AuditEventType.REMEDIATION_EXECUTE, approver, approver_role, plan.recovery_verification_notes)
                raise
            self.verify_recovery(plan_id)
            return self.get_plan(plan_id)

    def reject_plan(self, plan_id, reviewer, reviewer_role, reason):
        self._reviewer(reviewer, reviewer_role)
        with self._lock:
            plan = self.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Remediation plan '{plan_id}' does not exist.")
            if plan.state != RemediationState.PENDING_APPROVAL:
                raise ValueError("Only pending plans can be rejected.")
            plan.state, plan.rejected_by, plan.rejection_reason = RemediationState.REJECTED, reviewer, reason
            self._persist(plan, AuditEventType.REMEDIATION_APPROVAL, reviewer, reviewer_role, f"Rejected {plan_id}: {reason}")
            return plan

    def _execute_action(self, plan):
        """All catalog actions model recovery; they do not mutate a Kubernetes cluster."""
        chaos_controller.remove_fault(plan.target_service)
        for service in [plan.target_service] + plan.safety_blast_radius:
            telemetry_stream.flush_service_history(service)
        for _ in range(5):
            simulation_engine.simulate_cycle()

    def verify_recovery(self, plan_id):
        with self._lock:
            plan = self.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Remediation plan '{plan_id}' does not exist.")
            if plan.state not in {RemediationState.EXECUTING, RemediationState.FAILED_VERIFICATION, RemediationState.VERIFIED_SUCCESSFUL} or not plan.approved_by or not plan.executed_at:
                raise ValueError("Verification requires an approved, executed plan.")
            services = [plan.target_service] + plan.safety_blast_radius
            healthy = True
            for service in services:
                summary = telemetry_stream.get_service_summary(service)
                points = telemetry_stream.get_recent_points(service, limit=5)
                healthy = healthy and (
                    len(points) >= 5 and all(point.timestamp >= plan.executed_at for point in points)
                    and summary.last_heartbeat is not None
                    and (datetime.now(timezone.utc) - summary.last_heartbeat).total_seconds() <= settings.heartbeat_interval_sec * 3
                    and summary.status.value == "HEALTHY"
                    and summary.error_rate <= settings.anomaly_error_rate_threshold
                    and summary.p95_latency_ms <= settings.anomaly_latency_p95_ms
                )
            plan.verified_at = datetime.now(timezone.utc)
            plan.state = RemediationState.VERIFIED_SUCCESSFUL if healthy else RemediationState.FAILED_VERIFICATION
            plan.recovery_verification_notes = "Fresh post-execution samples and all affected services are healthy." if healthy else "Recovery criteria failed; no rollback was performed."
            with SessionLocal.begin() as session:
                self._save(session, plan)
                if healthy:
                    row = session.get(IncidentModel, plan.incident_id)
                    if row:
                        incident = incident_service._from_row(row)
                        if incident.state == IncidentState.REMEDIATING:
                            incident.state = IncidentState.RESOLVED
                            incident.updated_at = incident.resolved_at = plan.verified_at
                            incident.timeline.append(IncidentTimelineEvent(actor=plan.approved_by,
                                action="Recovery verified", from_state=IncidentState.REMEDIATING,
                                to_state=IncidentState.RESOLVED, note=plan.recovery_verification_notes))
                            incident_service._save(session, incident)
                            audit_service.record_event(AuditEventType.INCIDENT_TRANSITION, plan.approved_by, "SYSTEM",
                                                       incident.incident_id, "Resolved after verified remediation", {"plan_id": plan_id}, session)
                audit_service.record_event(AuditEventType.REMEDIATION_EXECUTE, "verification", "SYSTEM",
                                           plan.target_service, plan.recovery_verification_notes,
                                           {"plan_id": plan_id, "recovered": healthy}, session)
            return healthy

    def get_plan(self, plan_id):
        with SessionLocal() as session:
            row = session.get(RemediationPlanModel, plan_id)
            return self._from_row(row) if row else None

    def list_plans(self, state=None):
        with SessionLocal() as session:
            plans = [self._from_row(row) for row in session.query(RemediationPlanModel).all()]
        if state:
            plans = [plan for plan in plans if plan.state == state]
        return sorted(plans, key=lambda plan: plan.created_at, reverse=True)

remediation_engine = RemediationEngine()
