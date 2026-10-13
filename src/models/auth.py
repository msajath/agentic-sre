"""
Authentication and Role-Based Access Control (RBAC) Data Models.
Protects sensitive platform actions behind strict cryptographic tokens and scoped roles.
"""

from enum import Enum
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRole(str, Enum):
    ADMIN = "ADMIN"          # Full cluster & security administration
    SRE_LEAD = "SRE_LEAD"    # Incident remediation approvals, chaos tests, triage
    OPERATOR = "OPERATOR"    # Incident triage, acknowledge, notes, manual alerts
    VIEWER = "VIEWER"        # Read-only telemetry, topology, and audit log viewer


class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    role: UserRole = UserRole.OPERATOR
    hashed_password: str
    salt: str
    full_name: str
    is_active: bool = True


class UserPublic(BaseModel):
    username: str
    email: EmailStr
    role: UserRole
    full_name: str
    is_active: bool


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr = Field(..., max_length=128)
    full_name: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Full name is required.")
        return name


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    username: str
    expires_in_sec: int


class TokenPayload(BaseModel):
    sub: str
    role: UserRole
    exp: int
    iat: int
