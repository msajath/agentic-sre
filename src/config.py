"""
Configuration module for the Agentic SRE Platform.
Employs Pydantic for strict schema validation, type safety, and environment isolation.
"""

from typing import List
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Agentic SRE Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    
    # Server host & port
    host: str = "127.0.0.1"
    port: int = 8000
    
    # Telemetry & Monitoring Settings
    heartbeat_interval_sec: float = 2.0
    telemetry_window_size: int = 100
    anomaly_error_rate_threshold: float = 0.05  # 5% error rate triggers warning/anomaly
    anomaly_latency_p95_ms: float = 800.0       # >800ms triggers latency warning
    
    # Security Configurations
    allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8000", 
            "http://localhost:8000",
            "http://localhost:5173",
            "http://127.0.0.1:5173"
        ]
    )
    secret_key: str = "agentic-sre-insecure-dev-key-change-in-prod"
    token_expire_minutes: int = 60
    
    # Simulated Cluster Services
    managed_services: List[str] = Field(
        default_factory=lambda: [
            "auth-service",
            "order-service",
            "payment-service",
            "inventory-service",
            "notification-service",
        ]
    )


settings = Settings()
