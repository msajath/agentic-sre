"""
Chaos engineering fault injection models and validation schemas.
Guarantees fault parameters are strictly bound within safe simulation limits.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


class FaultType(str, Enum):
    LATENCY = "LATENCY"
    ERROR_STORM = "ERROR_STORM"
    SERVICE_CRASH = "SERVICE_CRASH"
    RESOURCE_SATURATION = "RESOURCE_SATURATION"
    DATABASE_LOCK = "DATABASE_LOCK"


class ChaosInjectionRequest(BaseModel):
    service_name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    fault_type: FaultType
    magnitude: float = Field(
        default=1.0,
        ge=0.0,
        le=10000.0,
        description="Magnitude of fault (e.g., latency delay ms, error rate percentage 0-100, resource load)",
    )
    duration_sec: int = Field(
        default=30,
        ge=5,
        le=600,
        description="Duration in seconds before fault auto-expires safely",
    )
    injected_by: str = Field(default="sre-operator", max_length=64)

    @field_validator("service_name")
    @classmethod
    def sanitize_service_name(cls, v: str) -> str:
        return v.strip().lower()


class ActiveFault(BaseModel):
    fault_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    service_name: str
    fault_type: FaultType
    magnitude: float
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    is_active: bool = True
    injected_by: str = "sre-operator"
