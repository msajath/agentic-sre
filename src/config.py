"""Validated environment configuration for the simulation platform."""
import json
import os
import secrets
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from src import environment as _environment  # noqa: F401 - load local configuration before reading variables

class Settings(BaseModel):
    app_name: str = "Agentic SRE Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    simulation_enabled: bool = True
    heartbeat_interval_sec: float = Field(default=2.0, gt=0)
    telemetry_window_size: int = Field(default=100, ge=5, le=10000)
    anomaly_error_rate_threshold: float = Field(default=0.05, gt=0, lt=1)
    anomaly_latency_p95_ms: float = Field(default=800.0, gt=0)
    allowed_origins: List[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ])
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48), min_length=32)
    token_expire_minutes: int = Field(default=60, ge=1, le=1440)
    bootstrap_admin_password: Optional[str] = Field(default=None, min_length=12, max_length=128, exclude=True)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    managed_services: List[str] = Field(default_factory=lambda: [
        "auth-service", "order-service", "payment-service",
        "inventory-service", "notification-service",
    ])

    @model_validator(mode="after")
    def validate_production(self):
        if self.environment.lower() == "production" and "secret_key" not in self.model_fields_set:
            raise ValueError("Production requires SECRET_KEY (at least 32 characters).")
        if self.secret_key == "agentic-sre-insecure-dev-key-change-in-prod":
            raise ValueError("The old development JWT signing key is prohibited.")
        if "*" in self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS must list explicit origins.")
        return self

    @classmethod
    def from_env(cls):
        values = {}
        for name in cls.model_fields:
            variable = "SRE_DEBUG" if name == "debug" else name.upper()
            value = os.getenv("SRE_" + name.upper(), os.getenv(variable))
            if name == "bootstrap_admin_password" and value == "":
                value = None
            if value is not None:
                values[name] = json.loads(value) if name in {"allowed_origins", "managed_services"} else value
        return cls.model_validate(values)

settings = Settings.from_env()
