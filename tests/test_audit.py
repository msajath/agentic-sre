"""
Unit & Cryptographic Security Tests for Immutable Audit Ledger.
"""

from src.models.audit import AuditEventType
from src.services.audit_service import audit_service


def test_audit_event_recording():
    """Verify events are correctly appended and chained with SHA-256."""
    entry = audit_service.record_event(
        event_type=AuditEventType.CHAOS_INJECT,
        actor="lead",
        actor_role="SRE_LEAD",
        target_resource="order-service",
        action_summary="Injected test latency",
        details={"magnitude": 1000},
    )
    assert entry.entry_hash is not None
    assert len(entry.entry_hash) == 64  # SHA-256 hex string length
    assert entry.prev_hash is not None


def test_audit_chain_integrity_verification():
    """Verify cryptographic hash-chain validates successfully."""
    report = audit_service.verify_integrity()
    assert report.is_valid is True
    assert report.genesis_verified is True
    assert report.tampered_entry_id is None
    assert report.total_entries >= 1


def test_audit_tamper_detection():
    """
    Simulate an adversary attempting to alter an audit record:
    Verifies the cryptographic chain instantly catches the tampering!
    """
    # Record a test entry
    entry = audit_service.record_event(
        event_type=AuditEventType.INCIDENT_NOTE,
        actor="attacker",
        actor_role="OPERATOR",
        target_resource="payment-service",
        action_summary="Normal looking note",
        details={"data": "original"},
    )

    # Tamper with the details directly in memory without updating the hash
    entry.action_summary = "TAMPERED: Attacker deleted evidence!"

    # Verify integrity now catches the tampering
    report = audit_service.verify_integrity()
    assert report.is_valid is False
    assert report.tampered_entry_id == entry.log_id
    assert "hash signature mismatch" in report.message

    # Restore original for subsequent tests
    entry.action_summary = "Normal looking note"
    entry.entry_hash = entry.compute_hash()
    assert audit_service.verify_integrity().is_valid is True
