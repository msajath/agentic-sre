"""
Approval-Gated Automated Remediation Engine with Recovery Verification.
Guarantees human oversight, bounded action catalog, and post-execution verification.
"""

from datetime import datetime, timezone
import json
import threading
from typing import Dict, List, Optional

from src.database import RemediationPlanModel, SessionLocal
from src.models.audit import AuditEventType
from src.models.incident import IncidentState
from src.models.remediation import (
    RemediationActionType,
    RemediationPlan,
    RemediationState,
)
from src.services.audit_service import audit_service
from src.services.chaos_controller import chaos_controller
from src.services.incident_service import incident_service
from src.services.simulation_engine import simulation_engine
from src.services.telemetry_stream import telemetry_stream
from src.services.topology_graph import topology_engine


class RemediationEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._plans: Dict[str, RemediationPlan] = {}
        self._load_from_db()

    def _load_from_db(self):
        """Hydrates remediation plans from SQLite."""
        with SessionLocal() as session:
            try:
                for row in session.query(RemediationPlanModel).all():
                    created_at = row.created_at.replace(tzinfo=timezone.utc) if row.created_at and row.created_at.tzinfo is None else row.created_at
                    executed_at = row.executed_at.replace(tzinfo=timezone.utc) if row.executed_at and row.executed_at.tzinfo is None else row.executed_at
                    verified_at = row.verified_at.replace(tzinfo=timezone.utc) if row.verified_at and row.verified_at.tzinfo is None else row.verified_at
                    self._plans[row.plan_id] = RemediationPlan(
                        plan_id=row.plan_id,
                        incident_id=row.incident_id,
                        target_service=row.target_service,
                        action_type=RemediationActionType(row.action_type),
                        parameters=json.loads(row.parameters),
                        state=RemediationState(row.state),
                        proposed_by=row.proposed_by,
                        approved_by=row.approved_by,
                        rejected_by=row.rejected_by,
                        rejection_reason=row.rejection_reason,
                        safety_blast_radius=json.loads(row.safety_blast_radius),
                        created_at=created_at,
                        executed_at=executed_at,
                        verified_at=verified_at,
                        recovery_verification_notes=row.recovery_verification_notes,
                    )
            except Exception as e:
                print(f"[Remediation DB Hydration Warning] {e}")

    def _save_plan_to_db(self, plan: RemediationPlan):
        """Upserts a remediation plan into SQLite."""
        with SessionLocal() as session:
            try:
                row = session.query(RemediationPlanModel).filter_by(plan_id=plan.plan_id).first()
                params_json = json.dumps(plan.parameters)
                blast_json = json.dumps(plan.safety_blast_radius)

                if not row:
                    row = RemediationPlanModel(
                        plan_id=plan.plan_id,
                        incident_id=plan.incident_id,
                        target_service=plan.target_service,
                        action_type=plan.action_type.value,
                        parameters=params_json,
                        state=plan.state.value,
                        proposed_by=plan.proposed_by,
                        approved_by=plan.approved_by,
                        rejected_by=plan.rejected_by,
                        rejection_reason=plan.rejection_reason,
                        safety_blast_radius=blast_json,
                        created_at=plan.created_at,
                        executed_at=plan.executed_at,
                        verified_at=plan.verified_at,
                        recovery_verification_notes=plan.recovery_verification_notes,
                    )
                    session.add(row)
                else:
                    row.state = plan.state.value
                    row.approved_by = plan.approved_by
                    row.rejected_by = plan.rejected_by
                    row.rejection_reason = plan.rejection_reason
                    row.executed_at = plan.executed_at
                    row.verified_at = plan.verified_at
                    row.recovery_verification_notes = plan.recovery_verification_notes
                session.commit()
            except Exception as e:
                print(f"[Remediation DB Save Warning] {e}")

    def propose_plan(
        self,
        incident_id: str,
        target_service: str,
        action_type: RemediationActionType,
        parameters: Optional[Dict] = None,
        proposed_by: str = "agentic-rca-engine",
    ) -> RemediationPlan:
        """
        Generates a pending remediation plan awaiting human oversight.
        """
        if not topology_engine.is_service_registered(target_service):
            raise ValueError(f"Service '{target_service}' is not recognized in topology.")

        blast_radius = topology_engine.get_affected_dependents(target_service)

        plan = RemediationPlan(
            incident_id=incident_id,
            target_service=target_service,
            action_type=action_type,
            parameters=parameters or {},
            state=RemediationState.PENDING_APPROVAL,
            proposed_by=proposed_by,
            safety_blast_radius=blast_radius,
        )

        with self._lock:
            self._plans[plan.plan_id] = plan
            self._save_plan_to_db(plan)

        # Audit log the remediation proposal
        audit_service.record_event(
            event_type=AuditEventType.REMEDIATION_REQUEST,
            actor=proposed_by,
            actor_role="AGENTIC_ENGINE",
            target_resource=target_service,
            action_summary=f"Remediation plan {plan.plan_id} proposed: {action_type.value} on {target_service}",
            details={"incident_id": incident_id, "action": action_type.value, "blast_radius": blast_radius},
        )

        return plan

    def approve_and_execute(
        self,
        plan_id: str,
        approver: str,
        approver_role: str,
        reason: str,
    ) -> RemediationPlan:
        """
        Human-in-the-loop gate: Approves and immediately executes the remediation action safely,
        followed by post-execution health recovery verification.
        """
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise KeyError(f"Remediation plan '{plan_id}' does not exist.")

            if plan.state != RemediationState.PENDING_APPROVAL:
                raise ValueError(f"Plan '{plan_id}' is in state '{plan.state.value}', not PENDING_APPROVAL.")

            now = datetime.now(timezone.utc)
            plan.state = RemediationState.APPROVED
            plan.approved_by = approver
            plan.executed_at = now
            self._save_plan_to_db(plan)

        # Record approval in audit ledger
        audit_service.record_event(
            event_type=AuditEventType.REMEDIATION_APPROVAL,
            actor=approver,
            actor_role=approver_role,
            target_resource=plan.target_service,
            action_summary=f"Remediation plan {plan_id} APPROVED by {approver}: {reason}",
            details={"plan_id": plan_id, "reason": reason},
        )

        # Execute safe remediation action
        self._execute_action(plan)

        # Verify post-remediation health recovery
        self.verify_recovery(plan_id)

        return plan

    def reject_plan(
        self,
        plan_id: str,
        reviewer: str,
        reviewer_role: str,
        reason: str,
    ) -> RemediationPlan:
        """Human-in-the-loop gate: Rejects proposed remediation plan."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise KeyError(f"Remediation plan '{plan_id}' does not exist.")

            if plan.state != RemediationState.PENDING_APPROVAL:
                raise ValueError(f"Plan '{plan_id}' cannot be rejected in state '{plan.state.value}'.")

            plan.state = RemediationState.REJECTED
            plan.rejected_by = reviewer
            plan.rejection_reason = reason
            self._save_plan_to_db(plan)

        audit_service.record_event(
            event_type=AuditEventType.REMEDIATION_APPROVAL,
            actor=reviewer,
            actor_role=reviewer_role,
            target_resource=plan.target_service,
            action_summary=f"Remediation plan {plan_id} REJECTED by {reviewer}: {reason}",
            details={"plan_id": plan_id, "reason": reason},
        )

        return plan

    def _execute_action(self, plan: RemediationPlan):
        """Executes bounded remediation action safely without dynamic code or shell execution."""
        svc = plan.target_service

        if plan.action_type in [
            RemediationActionType.RESTART_SERVICE,
            RemediationActionType.ROLLBACK_DEPLOYMENT,
            RemediationActionType.TRIP_CIRCUIT_BREAKER,
            RemediationActionType.SCALE_REPLICAS,
        ]:
            # Removes active simulated failure disruptions on target service
            chaos_controller.remove_fault(svc)
            telemetry_stream.flush_service_history(svc)
            # Also flush affected callers so their cascade metric slate resets
            for caller in topology_engine.get_affected_dependents(svc):
                telemetry_stream.flush_service_history(caller)

        # Trigger discrete simulation cycles to generate fresh healthy traffic immediately
        for _ in range(5):
            simulation_engine.simulate_cycle()

        audit_service.record_event(
            event_type=AuditEventType.REMEDIATION_EXECUTE,
            actor="remediation-runner",
            actor_role="SYSTEM_AUTOMATION",
            target_resource=svc,
            action_summary=f"Executed {plan.action_type.value} on {svc}",
            details={"plan_id": plan.plan_id},
        )

    def verify_recovery(self, plan_id: str) -> bool:
        """
        Post-remediation verification:
        Monitors target service metrics to verify error rates have dropped below thresholds.
        """
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False

        summary = telemetry_stream.get_service_summary(plan.target_service)
        now = datetime.now(timezone.utc)

        # Verify healthy metrics: error_rate < 5% and service not DOWN
        is_recovered = (summary.error_rate <= 0.05) and (summary.status.value != "DOWN")

        with self._lock:
            plan.verified_at = now
            if is_recovered:
                plan.state = RemediationState.VERIFIED_SUCCESSFUL
                plan.recovery_verification_notes = (
                    f"Health verified: Error rate is {summary.error_rate * 100:.1f}%, status is {summary.status.value}."
                )
            else:
                plan.state = RemediationState.FAILED_ROLLBACK
                plan.recovery_verification_notes = (
                    f"Verification failed: Error rate remains elevated at {summary.error_rate * 100:.1f}%."
                )
            self._save_plan_to_db(plan)

        # Automatically resolve associated incident if verified healthy!
        if is_recovered and plan.incident_id:
            try:
                incident = incident_service.get_incident(plan.incident_id)
                if incident and incident.state != IncidentState.RESOLVED:
                    # Transition through proper state machine if necessary
                    if incident.state == IncidentState.DETECTED:
                        incident_service.transition_state(
                            plan.incident_id, IncidentState.ACKNOWLEDGED, "Auto-ACK on remediation execution", "automation", "SYSTEM"
                        )
                    if incident.state in [IncidentState.DETECTED, IncidentState.ACKNOWLEDGED]:
                        incident_service.transition_state(
                            plan.incident_id, IncidentState.INVESTIGATING, "Investigating with active remediation", "automation", "SYSTEM"
                        )
                    incident_service.transition_state(
                        plan.incident_id,
                        IncidentState.RESOLVED,
                        f"Automated remediation {plan_id} executed and verified healthy.",
                        plan.approved_by or "lead",
                        "SRE_LEAD",
                    )
            except Exception as e:
                print(f"[Remediation Verification] Notice: Incident state update: {e}")

        return is_recovered

    def get_plan(self, plan_id: str) -> Optional[RemediationPlan]:
        with self._lock:
            return self._plans.get(plan_id)

    def list_plans(self, state: Optional[RemediationState] = None) -> List[RemediationPlan]:
        with self._lock:
            plans = list(self._plans.values())

        if state:
            plans = [p for p in plans if p.state == state]

        def get_sort_key(p):
            dt = p.created_at
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt or datetime.min.replace(tzinfo=timezone.utc)

        return sorted(plans, key=get_sort_key, reverse=True)


remediation_engine = RemediationEngine()
