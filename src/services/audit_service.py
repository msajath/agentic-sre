"""Tamper-evident audit chains, persisted in the same transaction as state changes.

A hash chain detects edits, not deletion of its tail by a database administrator.
Keep external backups/checkpoints for stronger tamper protection.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import threading
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from src.database import AuditLogModel, SessionLocal, lock_audit_chain
from src.models.audit import AuditEventType, AuditIntegrityReport, AuditLogEntry

GENESIS_HASH = "0" * 64

class AuditService:
    def __init__(self, persist_db: bool = True):
        self._lock = threading.RLock()
        self._persist_db = persist_db
        self._ledger: List[AuditLogEntry] = []
        if not persist_db:
            self.initialize()

    @staticmethod
    def _from_row(row):
        ts = row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp.tzinfo is None else row.timestamp
        return AuditLogEntry(log_id=row.log_id, timestamp=ts, event_type=row.event_type,
                             actor=row.actor, actor_role=row.actor_role, target_resource=row.target_resource,
                             action_summary=row.action_summary, details=json.loads(row.details),
                             prev_hash=row.prev_hash, entry_hash=row.entry_hash)

    @staticmethod
    def _row(entry):
        data = entry.model_dump(mode="python")
        data["event_type"] = entry.event_type.value
        data["details"] = json.dumps(entry.details)
        return AuditLogModel(**data)

    def initialize(self):
        with self._lock:
            genesis = AuditLogEntry(log_id="GENESIS-BLOCK", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                    event_type=AuditEventType.INCIDENT_CREATE, actor="SYSTEM_INIT", actor_role="ROOT",
                                    target_resource="agentic-sre-platform", action_summary="Audit Ledger Initialized with Cryptographic Chain",
                                    details={"platform_version": "0.1.0", "client": "Virtusa"}, prev_hash=GENESIS_HASH)
            genesis.entry_hash = genesis.compute_hash()
            if self._persist_db:
                with SessionLocal.begin() as session:
                    lock_audit_chain(session)
                    rows = session.query(AuditLogModel).all()
                    if not rows:
                        session.add(self._row(genesis))
                    elif not session.get(AuditLogModel, "GENESIS-BLOCK"):
                        # Repair only the known old first-boot omission, verified by the exact parent hash.
                        hashes = {row.entry_hash for row in rows}
                        missing_parents = {row.prev_hash for row in rows if row.prev_hash not in hashes}
                        if missing_parents == {genesis.entry_hash}:
                            session.add(self._row(genesis))
            elif not self._ledger:
                self._ledger.append(genesis)
            if not self.verify_integrity().is_valid:
                raise RuntimeError("Audit ledger integrity failed. Restore a trusted backup before starting.")

    def record_event(self, event_type: AuditEventType, actor: str, actor_role: str,
                     target_resource: str, action_summary: str, details: Optional[Dict[str, Any]] = None,
                     session=None) -> AuditLogEntry:
        with (nullcontext() if self._persist_db else self._lock):
            if self._persist_db and session is None:
                with SessionLocal.begin() as transaction:
                    lock_audit_chain(transaction)
                    return self.record_event(event_type, actor, actor_role, target_resource, action_summary, details, transaction)
            if self._persist_db:
                # Hold the PostgreSQL chain lock until the state transaction commits.
                session.flush()
                lock_audit_chain(session)
                referenced = select(AuditLogModel.prev_hash)
                heads = session.query(AuditLogModel).filter(~AuditLogModel.entry_hash.in_(referenced)).all()
                if len(heads) != 1:
                    raise RuntimeError("Audit ledger has no unique head.")
                previous_hash = heads[0].entry_hash
            else:
                previous_hash = self._ledger[-1].entry_hash
            entry = AuditLogEntry(event_type=event_type, actor=actor, actor_role=actor_role,
                                  target_resource=target_resource, action_summary=action_summary[:256],
                                  details=details or {}, prev_hash=previous_hash)
            entry.entry_hash = entry.compute_hash()
            if self._persist_db:
                session.add(self._row(entry))
                session.flush()
            else:
                self._ledger.append(entry)
            return entry

    def _entries(self):
        if not self._persist_db:
            return list(self._ledger)
        with SessionLocal() as session:
            entries = [self._from_row(row) for row in session.query(AuditLogModel).all()]
        # Chain pointers define order, even when timestamps are identical.
        by_prev = {}
        for entry in entries:
            if entry.prev_hash in by_prev:
                raise ValueError("Audit ledger contains a fork.")
            by_prev[entry.prev_hash] = entry
        ordered = []
        pointer = GENESIS_HASH
        while pointer in by_prev and len(ordered) < len(entries):
            entry = by_prev.pop(pointer)
            ordered.append(entry)
            pointer = entry.entry_hash
        if len(ordered) != len(entries):
            raise ValueError("Audit chain contains orphaned or cyclic entries.")
        return ordered

    def verify_integrity(self) -> AuditIntegrityReport:
        with self._lock:
            try:
                entries = self._entries()
            except ValueError as exc:
                return AuditIntegrityReport(is_valid=False, total_entries=0, genesis_verified=False, message=str(exc))
            if not entries:
                return AuditIntegrityReport(is_valid=False, total_entries=0, genesis_verified=False, message="Audit ledger is empty.")
            previous = GENESIS_HASH
            for index, entry in enumerate(entries):
                if (index == 0 and entry.log_id != "GENESIS-BLOCK") or entry.prev_hash != previous or entry.entry_hash != entry.compute_hash():
                    return AuditIntegrityReport(is_valid=False, total_entries=len(entries), genesis_verified=index > 0,
                                                tampered_entry_id=entry.log_id, message="Audit hash signature mismatch or broken chain.")
                previous = entry.entry_hash
            return AuditIntegrityReport(is_valid=True, total_entries=len(entries), genesis_verified=True,
                                        message="Audit hash chain verified against persisted entries.")

    def get_entries(self, limit: int = 50, event_type: Optional[AuditEventType] = None, actor: Optional[str] = None):
        with self._lock:
            entries = self._entries()[1:]
            if event_type:
                entries = [entry for entry in entries if entry.event_type == event_type]
            if actor:
                entries = [entry for entry in entries if entry.actor.lower() == actor.lower()]
            return list(reversed(entries))[:limit]

audit_service = AuditService()
