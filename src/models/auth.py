"""
Authentication and Role-Based Access Control (RBAC) Data Models.
Protects sensitive platform actions behind strict cryptographic tokens and scoped roles.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


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
