"""
Immutable, Cryptographically Chained Audit Ledger Models.
Every operational event is hashed with its previous entry to form a tamper-evident log chain.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    AUTH_LOGIN = "AUTH_LOGIN"
    AUTH_FAILURE = "AUTH_FAILURE"
    CHAOS_INJECT = "CHAOS_INJECT"
    CHAOS_CLEAR = "CHAOS_CLEAR"
    CHAOS_RESET = "CHAOS_RESET"
    INCIDENT_CREATE = "INCIDENT_CREATE"
    INCIDENT_TRANSITION = "INCIDENT_TRANSITION"
    INCIDENT_NOTE = "INCIDENT_NOTE"
    REMEDIATION_REQUEST = "REMEDIATION_REQUEST"
    REMEDIATION_APPROVAL = "REMEDIATION_APPROVAL"
    REMEDIATION_EXECUTE = "REMEDIATION_EXECUTE"


class AuditLogEntry(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: AuditEventType
    actor: str = Field(default="system", max_length=64)
    actor_role: str = Field(default="SYSTEM", max_length=32)
    target_resource: str = Field(..., max_length=128)
    action_summary: str = Field(..., max_length=256)
    details: Dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = Field(default="GENESIS_HASH_00000000000000000000000000000000")
    entry_hash: str = Field(default="")

    def compute_hash(self) -> str:
        """Computes cryptographic SHA-256 hash linking this entry to the previous entry."""
        payload = (
            f"{self.log_id}|"
            f"{self.timestamp.isoformat()}|"
            f"{self.event_type.value}|"
            f"{self.actor}|"
            f"{self.actor_role}|"
            f"{self.target_resource}|"
            f"{self.action_summary}|"
            f"{json.dumps(self.details, sort_keys=True)}|"
            f"{self.prev_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditIntegrityReport(BaseModel):
    is_valid: bool
    total_entries: int
    genesis_verified: bool
    tampered_entry_id: Optional[str] = None
    verification_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
