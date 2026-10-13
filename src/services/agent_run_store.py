"""Persist bounded investigation state after each stage for audit and reload."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from src.database import AgentRunModel, SessionLocal


class AgentRunStore:
    def start(self, incident_id: str, state: dict) -> str:
        run_id = uuid4().hex
        with SessionLocal.begin() as session:
            session.add(AgentRunModel(
                run_id=run_id, incident_id=incident_id, status="RUNNING",
                state=json.dumps(state),
            ))
        return run_id

    def save(self, run_id: str, state: dict, status: str) -> None:
        with SessionLocal.begin() as session:
            row = session.get(AgentRunModel, run_id)
            if row is None:
                raise KeyError("Investigation run was not found.")
            row.state = json.dumps(state)
            row.status = status
            row.updated_at = datetime.now(timezone.utc)

    def list_for_incident(self, incident_id: str, limit: int = 20) -> list[dict]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(AgentRunModel).where(AgentRunModel.incident_id == incident_id)
                .order_by(AgentRunModel.started_at.desc(), AgentRunModel.run_id.desc())
                .limit(limit)
            ).all()
            return [{
                "run_id": row.run_id,
                "incident_id": row.incident_id,
                "status": row.status,
                "state": json.loads(row.state),
                "started_at": row.started_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            } for row in rows]


agent_run_store = AgentRunStore()
