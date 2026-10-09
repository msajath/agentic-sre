"""
Production-Grade SQLite Database Layer with SQLAlchemy 2.0.
Ensures persistent, tamper-evident storage for incidents, audit ledgers, users, and remediations.
Enforces Write-Ahead Logging (WAL) and foreign keys for high-concurrency ACID transactions.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Data Directory
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "sre_platform.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLAlchemy Engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


# Enable SQLite WAL mode and foreign key constraints for production performance & integrity
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    username = Column(String(32), primary_key=True, index=True)
    email = Column(String(128), unique=True, nullable=False)
    role = Column(String(32), nullable=False)
    hashed_password = Column(String(256), nullable=False)
    salt = Column(String(64), nullable=False)
    full_name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)


class IncidentModel(Base):
    __tablename__ = "incidents"

    incident_id = Column(String(32), primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    state = Column(String(32), nullable=False, index=True)
    severity = Column(String(32), nullable=False, index=True)
    root_cause_service = Column(String(64), nullable=True)
    affected_services = Column(Text, default="[]")  # JSON string
    timeline = Column(Text, default="[]")           # JSON string
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_ledger"

    log_id = Column(String(64), primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor = Column(String(64), nullable=False)
    actor_role = Column(String(32), nullable=False)
    target_resource = Column(String(128), nullable=False)
    action_summary = Column(String(256), nullable=False)
    details = Column(Text, default="{}")  # JSON string
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False, index=True)


class RemediationPlanModel(Base):
    __tablename__ = "remediation_plans"

    plan_id = Column(String(32), primary_key=True, index=True)
    incident_id = Column(String(32), nullable=False, index=True)
    target_service = Column(String(64), nullable=False)
    action_type = Column(String(64), nullable=False)
    parameters = Column(Text, default="{}")        # JSON string
    state = Column(String(32), nullable=False, index=True)
    proposed_by = Column(String(64), nullable=False)
    approved_by = Column(String(64), nullable=True)
    rejected_by = Column(String(64), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    safety_blast_radius = Column(Text, default="[]") # JSON string
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    executed_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    recovery_verification_notes = Column(Text, nullable=True)


def init_db():
    """Initializes tables and confirms database accessibility."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency helper yielding transactional sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
