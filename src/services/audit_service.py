"""
Immutable, Cryptographically Chained Audit Ledger Service.
Maintains a tamper-evident blockchain-style hash chain for all administrative and operational actions.
"""

from datetime import datetime, timezone
import json
import threading
from typing import Any, Dict, List, Optional

from src.models.audit import (
    AuditEventType,
    AuditIntegrityReport,
    AuditLogEntry,
)

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


class AuditService:
    def __init__(self):
        self._lock = threading.Lock()
        self._ledger: List[AuditLogEntry] = []
        self._initialize_genesis_entry()

    def _initialize_genesis_entry(self):
        """Creates the immutable Genesis block of the audit ledger."""
        genesis = AuditLogEntry(
            log_id="GENESIS-BLOCK",
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.INCIDENT_CREATE,
            actor="SYSTEM_INIT",
            actor_role="ROOT",
            target_resource="agentic-sre-platform",
            action_summary="Audit Ledger Initialized with Cryptographic Chain",
            details={"platform_version": "0.1.0", "client": "Virtusa"},
            prev_hash=GENESIS_HASH,
        )
        genesis.entry_hash = genesis.compute_hash()
        self._ledger.append(genesis)

    def record_event(
        self,
        event_type: AuditEventType,
        actor: str,
        actor_role: str,
        target_resource: str,
        action_summary: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLogEntry:
        """
        Appends an event to the ledger, cryptographically binding it to the prior entry.
        """
        with self._lock:
            prev_entry = self._ledger[-1]
            entry = AuditLogEntry(
                event_type=event_type,
                actor=actor,
                actor_role=actor_role,
                target_resource=target_resource,
                action_summary=action_summary,
                details=details or {},
                prev_hash=prev_entry.entry_hash,
            )
            entry.entry_hash = entry.compute_hash()
            self._ledger.append(entry)
            return entry

    def verify_integrity(self) -> AuditIntegrityReport:
        """
        Validates the entire ledger from Genesis block to head.
        Verifies every individual hash and confirms backward chain pointers.
        """
        with self._lock:
            if not self._ledger:
                return AuditIntegrityReport(
                    is_valid=False,
                    total_entries=0,
                    genesis_verified=False,
                    message="Audit ledger is unexpectedly empty.",
                )

            # 1. Verify Genesis
            genesis = self._ledger[0]
            if genesis.log_id != "GENESIS-BLOCK" or genesis.prev_hash != GENESIS_HASH:
                return AuditIntegrityReport(
                    is_valid=False,
                    total_entries=len(self._ledger),
                    genesis_verified=False,
                    tampered_entry_id=genesis.log_id,
                    message="Genesis block was compromised or replaced.",
                )

            # 2. Verify subsequent blocks
            for i in range(1, len(self._ledger)):
                current = self._ledger[i]
                previous = self._ledger[i - 1]

                # Check pointer
                if current.prev_hash != previous.entry_hash:
                    return AuditIntegrityReport(
                        is_valid=False,
                        total_entries=len(self._ledger),
                        genesis_verified=True,
                        tampered_entry_id=current.log_id,
                        message=f"Hash chain broken between block {i-1} and {i} ({current.log_id}).",
                    )

                # Recompute hash
                expected_hash = current.compute_hash()
                if current.entry_hash != expected_hash:
                    return AuditIntegrityReport(
                        is_valid=False,
                        total_entries=len(self._ledger),
                        genesis_verified=True,
                        tampered_entry_id=current.log_id,
                        message=f"Block {current.log_id} payload altered; hash signature mismatch.",
                    )

            return AuditIntegrityReport(
                is_valid=True,
                total_entries=len(self._ledger),
                genesis_verified=True,
                message="Audit ledger integrity verified. All cryptographic signatures valid.",
            )

    def get_entries(
        self,
        limit: int = 50,
        event_type: Optional[AuditEventType] = None,
        actor: Optional[str] = None,
    ) -> List[AuditLogEntry]:
        """Returns filtered audit log entries in reverse chronological order."""
        with self._lock:
            # Skip genesis from standard presentation unless requested
            entries = self._ledger[1:]
            
            if event_type:
                entries = [e for e in entries if e.event_type == event_type]
            if actor:
                entries = [e for e in entries if e.actor.lower() == actor.lower()]
                
            return list(reversed(entries))[:limit]


audit_service = AuditService()
