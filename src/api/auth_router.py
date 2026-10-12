"""
Authentication and Identity Management API Router.
Handles secure token issuance, credentials verification, and RBAC profile retrieval.
"""

import threading
import time
from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.models.audit import AuditEventType
from src.models.auth import LoginRequest, TokenResponse, User, UserPublic
from src.services.audit_service import audit_service
from src.services.auth_service import auth_service, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Identity"])


class LoginAttemptLimiter:
    """Bound failed password attempts per client and account in this single-process app."""
    def __init__(self):
        self._failures = {}
        self._lock = threading.Lock()

    def blocked(self, key: tuple[str, str]) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [when for when in self._failures.get(key, ()) if now - when < 60]
            if recent:
                self._failures[key] = recent
            else:
                self._failures.pop(key, None)
            return len(recent) >= 5

    def failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            if key not in self._failures and len(self._failures) >= 4096:
                self._failures.pop(next(iter(self._failures)))
            self._failures.setdefault(key, []).append(time.monotonic())

    def clear(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request):
    """
    Authenticates user with username & password and issues signed HMAC-SHA256 JWT.
    """
    key = (http_request.client.host if http_request.client else "unknown", request.username.lower())
    if login_attempt_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again in one minute.",
                            headers={"Retry-After": "60"})
    user = auth_service.authenticate_user(request.username, request.password)
    if not user:
        login_attempt_limiter.failure(key)
        # Audit log failed login attempt
        audit_service.record_event(
            event_type=AuditEventType.AUTH_FAILURE,
            actor=request.username,
            actor_role="ANONYMOUS",
            target_resource="auth-gateway",
            action_summary=f"Failed login attempt for user: {request.username}",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_attempt_limiter.clear(key)
    token = auth_service.create_access_token(user)

    # Audit log successful login
    audit_service.record_event(
        event_type=AuditEventType.AUTH_LOGIN,
        actor=user.username,
        actor_role=user.role.value,
        target_resource="auth-gateway",
        action_summary=f"User {user.username} ({user.role.value}) logged in successfully.",
    )

    return token


@router.get("/me", response_model=UserPublic)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    Returns authenticated user profile and assigned RBAC permissions.
    """
    return UserPublic(
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )
