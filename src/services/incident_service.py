"""Transactional incident lifecycle and deduplicated detection."""
from datetime import datetime, timezone
import json
import threading
from typing import List, Optional
from src.database import IncidentModel, SessionLocal
from src.models.audit import AuditEventType
from src.models.incident import IncidentRecord, IncidentSeverity, IncidentState, IncidentTimelineEvent
from src.services.audit_service import audit_service

VALID_TRANSITIONS = {
    IncidentState.DETECTED: {IncidentState.ACKNOWLEDGED, IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.ACKNOWLEDGED: {IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.INVESTIGATING: {IncidentState.PENDING_APPROVAL, IncidentState.REMEDIATING, IncidentState.RESOLVED, IncidentState.CLOSED},
    IncidentState.PENDING_APPROVAL: {IncidentState.REMEDIATING, IncidentState.INVESTIGATING, IncidentState.CLOSED},
    IncidentState.REMEDIATING: {IncidentState.RESOLVED, IncidentState.INVESTIGATING},
    IncidentState.RESOLVED: {IncidentState.CLOSED, IncidentState.INVESTIGATING},
    IncidentState.CLOSED: {IncidentState.INVESTIGATING},
}

class IncidentService:
    def __init__(self):
        self._lock = threading.RLock()

    def initialize(self):
        self.list_incidents()  # Validate persisted records; errors stop startup.

    @staticmethod
    def _from_row(row):
        data = {key: getattr(row, key) for key in (
            "incident_id", "title", "description", "state", "severity", "root_cause_service",
            "created_at", "updated_at", "resolved_at")}
        for key in ("created_at", "updated_at", "resolved_at"):
            if data[key] and data[key].tzinfo is None:
                data[key] = data[key].replace(tzinfo=timezone.utc)
        data["affected_services"] = json.loads(row.affected_services)
        data["timeline"] = json.loads(row.timeline)
        return IncidentRecord(**data)

    @staticmethod
    def _save(session, incident):
        row = session.get(IncidentModel, incident.incident_id) or IncidentModel(incident_id=incident.incident_id)
        for key in ("title", "description", "root_cause_service", "created_at", "updated_at", "resolved_at"):
            setattr(row, key, getattr(incident, key))
        row.state, row.severity = incident.state.value, incident.severity.value
        row.affected_services = json.dumps(incident.affected_services)
        row.timeline = json.dumps([event.model_dump(mode="json") for event in incident.timeline])
        session.add(row)
        session.flush()

    def create_incident(self, title: str, description: str, severity: IncidentSeverity = IncidentSeverity.MEDIUM,
                        root_cause_service: Optional[str] = None, affected_services: Optional[List[str]] = None,
                        actor: str = "system", actor_role: str = "SYSTEM") -> IncidentRecord:
        incident = IncidentRecord(title=title, description=description, severity=severity,
                                  root_cause_service=root_cause_service, affected_services=affected_services or [])
        incident.timeline.append(IncidentTimelineEvent(actor=actor, action="Incident Created",
                                                      to_state=IncidentState.DETECTED, note=description))
        with self._lock, SessionLocal.begin() as session:
            self._save(session, incident)
            audit_service.record_event(AuditEventType.INCIDENT_CREATE, actor, actor_role, incident.incident_id,
                                       f"Incident created: {title}", {"severity": incident.severity.value,
                                       "root_cause": root_cause_service, "affected_services": incident.affected_services}, session)
        return incident

    def capture_detection(self, candidate: IncidentRecord) -> IncidentRecord:
        """Keep one active persisted incident per root service and affected service set."""
        with self._lock:
            for incident in self.list_incidents():
                if (incident.state not in {IncidentState.RESOLVED, IncidentState.CLOSED}
                    and incident.root_cause_service == candidate.root_cause_service
                    and set(incident.affected_services) == set(candidate.affected_services)):
                    return incident
            return self.create_incident(candidate.title, candidate.description, candidate.severity,
                                        candidate.root_cause_service, candidate.affected_services)

    def transition_state(self, incident_id: str, target_state: IncidentState, reason: str, actor: str, actor_role: str):
        target_state = IncidentState(target_state)
        with self._lock, SessionLocal.begin() as session:
            row = session.get(IncidentModel, incident_id)
            if not row:
                raise KeyError(f"Incident with ID '{incident_id}' does not exist.")
            incident = self._from_row(row)
            previous = incident.state
            if target_state not in VALID_TRANSITIONS[previous]:
                raise ValueError(f"Illegal lifecycle transition from '{previous.value}' to '{target_state.value}'.")
            incident.state = target_state
            incident.updated_at = datetime.now(timezone.utc)
            incident.resolved_at = incident.updated_at if target_state == IncidentState.RESOLVED else None
            incident.timeline.append(IncidentTimelineEvent(actor=actor, action=f"Transitioned state from {previous.value} to {target_state.value}",
                                                          from_state=previous, to_state=target_state, note=reason))
            self._save(session, incident)
            audit_service.record_event(AuditEventType.INCIDENT_TRANSITION, actor, actor_role, incident_id,
                                       f"Incident {incident_id} state changed: {previous.value} -> {target_state.value}",
                                       {"reason": reason}, session)
        return incident

    def add_note(self, incident_id: str, note: str, actor: str, actor_role: str):
        with self._lock, SessionLocal.begin() as session:
            row = session.get(IncidentModel, incident_id)
            if not row:
                raise KeyError(f"Incident with ID '{incident_id}' does not exist.")
            incident = self._from_row(row)
            incident.timeline.append(IncidentTimelineEvent(actor=actor, action="Triage Note Added", note=note))
            incident.updated_at = datetime.now(timezone.utc)
            self._save(session, incident)
            audit_service.record_event(AuditEventType.INCIDENT_NOTE, actor, actor_role, incident_id,
                                       f"Triage note added by {actor}", {"note": note}, session)
        return incident

    def get_incident(self, incident_id):
        with SessionLocal() as session:
            row = session.get(IncidentModel, incident_id)
            return self._from_row(row) if row else None

    def list_incidents(self, state=None, severity=None, service=None):
        with SessionLocal() as session:
            incidents = [self._from_row(row) for row in session.query(IncidentModel).all()]
        if state:
            incidents = [incident for incident in incidents if incident.state == state]
        if severity:
            incidents = [incident for incident in incidents if incident.severity == severity]
        if service:
            incidents = [incident for incident in incidents if service.lower() in incident.affected_services
                         or incident.root_cause_service == service.lower()]
        return sorted(incidents, key=lambda incident: incident.updated_at, reverse=True)

incident_service = IncidentService()
