"""
Incident Lifecycle Management and State Machine Engine.
Enforces auditable state transitions, SLA tracking, and forensic timelines.
"""

from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional

from src.models.audit import AuditEventType
from src.models.incident import (
    IncidentRecord,
    IncidentSeverity,
    IncidentState,
    IncidentTimelineEvent,
)
from src.services.audit_service import audit_service


# State Machine Transition Rules
VALID_TRANSITIONS = {
    IncidentState.DETECTED: {IncidentState.ACKNOWLEDGED, IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.ACKNOWLEDGED: {IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.INVESTIGATING: {IncidentState.PENDING_APPROVAL, IncidentState.REMEDIATING, IncidentState.RESOLVED, IncidentState.CLOSED},
    IncidentState.PENDING_APPROVAL: {IncidentState.REMEDIATING, IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.REMEDIATING: {IncidentState.RESOLVED, IncidentState.INVESTIGATING},
    IncidentState.RESOLVED: {IncidentState.CLOSED, IncidentState.INVESTIGATING},
    IncidentState.CLOSED: {IncidentState.INVESTIGATING},  # Can reopen if symptoms recur
}


class IncidentService:
    def __init__(self):
        self._lock = threading.Lock()
        self._incidents: Dict[str, IncidentRecord] = {}

    def create_incident(
        self,
        title: str,
        description: str,
        severity: IncidentSeverity = IncidentSeverity.MEDIUM,
        root_cause_service: Optional[str] = None,
        affected_services: Optional[List[str]] = None,
        actor: str = "system",
        actor_role: str = "SYSTEM",
    ) -> IncidentRecord:
        """Instantiates a new incident and records initial audit timeline."""
        with self._lock:
            incident = IncidentRecord(
                title=title,
                description=description,
                severity=severity,
                root_cause_service=root_cause_service,
                affected_services=affected_services or [],
                state=IncidentState.DETECTED,
            )

            # Record initial timeline event
            incident.timeline.append(
                IncidentTimelineEvent(
                    actor=actor,
                    action="Incident Created",
                    to_state=IncidentState.DETECTED,
                    note=description,
                )
            )

            self._incidents[incident.incident_id] = incident

        # Record cryptographically chained audit log
        audit_service.record_event(
            event_type=AuditEventType.INCIDENT_CREATE,
            actor=actor,
            actor_role=actor_role,
            target_resource=incident.incident_id,
            action_summary=f"Incident created: {incident.title}",
            details={
                "severity": incident.severity.value,
                "root_cause": root_cause_service,
                "affected_services": affected_services,
            },
        )

        return incident

    def transition_state(
        self,
        incident_id: str,
        target_state: IncidentState,
        reason: str,
        actor: str,
        actor_role: str,
    ) -> IncidentRecord:
        """
        Transitions an incident to a new state following state-machine rules.
        """
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                raise KeyError(f"Incident with ID '{incident_id}' does not exist.")

            current_state = incident.state
            allowed_next = VALID_TRANSITIONS.get(current_state, set())

            if target_state not in allowed_next:
                raise ValueError(
                    f"Illegal lifecycle transition from '{current_state.value}' to '{target_state.value}'. "
                    f"Allowed transitions: {[s.value for s in allowed_next]}"
                )

            now = datetime.now(timezone.utc)
            incident.state = target_state
            incident.updated_at = now

            if target_state == IncidentState.RESOLVED:
                incident.resolved_at = now

            # Append to internal timeline
            incident.timeline.append(
                IncidentTimelineEvent(
                    actor=actor,
                    action=f"Transitioned state from {current_state.value} to {target_state.value}",
                    from_state=current_state,
                    to_state=target_state,
                    note=reason,
                )
            )

        # Audit log the state transition
        audit_service.record_event(
            event_type=AuditEventType.INCIDENT_TRANSITION,
            actor=actor,
            actor_role=actor_role,
            target_resource=incident_id,
            action_summary=f"Incident {incident_id} state changed: {current_state.value} -> {target_state.value}",
            details={"from_state": current_state.value, "to_state": target_state.value, "reason": reason},
        )

        return incident

    def add_note(
        self,
        incident_id: str,
        note: str,
        actor: str,
        actor_role: str,
    ) -> IncidentRecord:
        """Adds a collaborative triage note to the incident timeline."""
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                raise KeyError(f"Incident with ID '{incident_id}' does not exist.")

            now = datetime.now(timezone.utc)
            incident.updated_at = now
            incident.timeline.append(
                IncidentTimelineEvent(
                    actor=actor,
                    action="Triage Note Added",
                    from_state=incident.state,
                    to_state=incident.state,
                    note=note,
                )
            )

        audit_service.record_event(
            event_type=AuditEventType.INCIDENT_NOTE,
            actor=actor,
            actor_role=actor_role,
            target_resource=incident_id,
            action_summary=f"Triage note added by {actor}",
            details={"note_snippet": note[:100]},
        )

        return incident

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        with self._lock:
            return self._incidents.get(incident_id)

    def list_incidents(
        self,
        state: Optional[IncidentState] = None,
        severity: Optional[IncidentSeverity] = None,
        service: Optional[str] = None,
    ) -> List[IncidentRecord]:
        """Lists incidents filtered by state, severity, or affected service."""
        with self._lock:
            incidents = list(self._incidents.values())

        if state:
            incidents = [inc for inc in incidents if inc.state == state]
        if severity:
            incidents = [inc for inc in incidents if inc.severity == severity]
        if service:
            incidents = [
                inc for inc in incidents
                if service.lower() in [s.lower() for s in inc.affected_services]
                or (inc.root_cause_service and inc.root_cause_service.lower() == service.lower())
            ]

        # Return sorted by updated_at desc
        return sorted(incidents, key=lambda i: i.updated_at, reverse=True)


incident_service = IncidentService()
