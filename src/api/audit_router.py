"""
Cryptographic Audit Ledger API Router.
Exposes tamper-evident action logs and on-demand SHA-256 chain verification.
"""

from typing import List, Optional
import json
from fastapi import APIRouter, Query

from src.models.audit import AuditEventType, AuditIntegrityReport, AuditLogEntry
from src.services.audit_service import audit_service
from src.database import PlatformRecordModel, SessionLocal

router = APIRouter(prefix="/api/v1/audit", tags=["Audit Ledger"])


@router.get("/legacy")
async def get_legacy_audit_archive(limit: int = Query(default=50, ge=1, le=200)):
    """Unverified legacy history is separate from the current verified ledger."""
    with SessionLocal() as session:
        summary = session.get(PlatformRecordModel, "migration:postgres-audit-archive")
        rows = session.query(PlatformRecordModel).filter(
            PlatformRecordModel.key.startswith("legacy-audit:")
        ).order_by(PlatformRecordModel.key).limit(limit).all()
        return {"verified": False, "summary": json.loads(summary.payload) if summary else None,
                "records": [json.loads(row.payload) for row in rows]}


@router.get("/logs", response_model=List[AuditLogEntry])
async def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    event_type: Optional[AuditEventType] = Query(default=None),
    actor: Optional[str] = Query(default=None),
):
    """
    Returns cryptographically chained audit log ledger entries.
    """
    return audit_service.get_entries(limit=limit, event_type=event_type, actor=actor)


@router.get("/verify", response_model=AuditIntegrityReport)
async def verify_ledger_cryptographic_integrity():
    """
    Executes real-time verification of the SHA-256 blockchain hash integrity.
    Detects any retroactive modifications, tampering, or broken chain pointers.
    """
    return audit_service.verify_integrity()
