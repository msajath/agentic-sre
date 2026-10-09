"""
Authentication and Identity Management API Router.
Handles secure token issuance, credentials verification, and RBAC profile retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.models.audit import AuditEventType
from src.models.auth import LoginRequest, TokenResponse, User, UserPublic
from src.services.audit_service import audit_service
from src.services.auth_service import auth_service, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Identity"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticates user with username & password and issues signed HMAC-SHA256 JWT.
    """
    user = auth_service.authenticate_user(request.username, request.password)
    if not user:
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
