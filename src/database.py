"""
PostgreSQL storage for a single-process simulation platform.
Ensures persistent, tamper-evident storage for incidents, audit ledgers, users, and remediations.
Prisma migrations own the database schema.
"""

from datetime import datetime, timezone
import os
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    String,
    Text,
    create_engine,
    inspect,
    text,
    Index,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from src import environment  # noqa: F401 - load local configuration before reading variables

def parse_database_url(value: str | None) -> URL:
    """Require an explicit PostgreSQL connection; never create a fallback database."""
    if not value or not value.strip():
        raise ValueError("DATABASE_URL is required. Set it to your PostgreSQL connection URL.")
    try:
        database_url = make_url(value)
    except (ArgumentError, ValueError, TypeError):
        raise ValueError("DATABASE_URL must be a valid PostgreSQL connection URL.") from None
    if database_url.drivername in {"postgres", "postgresql"}:
        database_url = database_url.set(drivername="postgresql+psycopg")
    if database_url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use PostgreSQL (postgresql://).")
    if not database_url.database:
        raise ValueError("DATABASE_URL must name a PostgreSQL database.")
    return database_url


DATABASE_URL = os.getenv("DATABASE_URL")
database_url = parse_database_url(DATABASE_URL)

# SQLAlchemy Engine
engine = create_engine(
    database_url,
    connect_args={"connect_timeout": 10, "options": "-c timezone=UTC"},
    pool_pre_ping=True,
    echo=False,
)


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


class PlatformRecordModel(Base):
    __tablename__ = "platform_records"
    key = Column(String(128), primary_key=True)
    payload = Column(Text, nullable=False)


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(32), primary_key=True)
    incident_id = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    state = Column(Text, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (Index("ix_agent_runs_incident_started", "incident_id", "started_at"),)


def init_db():
    """Require the PostgreSQL schema created by Prisma migrations."""
    missing = set(Base.metadata.tables) - set(inspect(engine).get_table_names())
    if missing:
        raise RuntimeError("PostgreSQL schema is not initialized. Run npm run db:migrate before starting the API.")


def lock_audit_chain(session):
    """Serialize chain appends until commit, including writes from other connections."""
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 731904260101})


def get_db() -> Generator[Session, None, None]:
    """Dependency helper yielding transactional sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
