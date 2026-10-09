"""
Telemetry data models and Pydantic schemas.
Ensures strict validation, preventing injection attacks and malformed payloads.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ServiceStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    DOWN = "DOWN"


class MetricType(str, Enum):
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"


class TelemetryPoint(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service_name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    endpoint: str = Field(default="/", max_length=128)
    status_code: int = Field(default=200, ge=100, le=599)
    latency_ms: float = Field(default=0.0, ge=0.0, le=60000.0)
    cpu_usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    memory_usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    error_message: Optional[str] = Field(default=None, max_length=512)

    @field_validator("service_name")
    @classmethod
    def sanitize_service_name(cls, v: str) -> str:
        return v.strip().lower()


class HeartbeatPayload(BaseModel):
    service_name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: ServiceStatus = Field(default=ServiceStatus.HEALTHY)
    active_instances: int = Field(default=1, ge=0, le=100)
    version: str = Field(default="1.0.0", max_length=32)
    metadata: Dict[str, str] = Field(default_factory=dict)


class ServiceMetricsSummary(BaseModel):
    service_name: str
    status: ServiceStatus
    total_requests: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    cpu_usage_pct: float
    memory_usage_pct: float
    active_faults: List[str] = Field(default_factory=list)
    last_heartbeat: Optional[datetime] = None
