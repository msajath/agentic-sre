"""
Unit & Security Tests for Authentication, Password Hashing, JWT, and RBAC.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from src.config import settings
from src.models.auth import UserRole
from src.services.auth_service import auth_service


def test_password_authentication():
    """Verify PBKDF2 salted hash validation."""
    # Valid credentials
    user = auth_service.authenticate_user(
        "admin", "test-admin-credential-2026"
    )
    assert user is not None
    assert user.username == "admin"
    assert user.role == UserRole.ADMIN

    # Invalid password
    assert auth_service.authenticate_user("admin", "WrongPassword") is None

    # Non-existent user
    assert auth_service.authenticate_user(
        "nonexistent", "test-admin-credential-2026"
    ) is None


def test_jwt_token_creation_and_verification():
    """Verify HMAC-SHA256 JWT creation, claims, and validation."""
    user = auth_service.get_user_by_username("lead")
    assert user is not None

    token_resp = auth_service.create_access_token(user)
    assert token_resp.access_token is not None
    assert token_resp.role == UserRole.SRE_LEAD
    assert token_resp.username == "lead"

    # Verify token
    payload = auth_service.verify_token(token_resp.access_token)
    assert payload.sub == "lead"
    assert payload.role == UserRole.SRE_LEAD


def test_tampered_jwt_rejected():
    """Verify cryptographic signature catches tampered tokens."""
    user = auth_service.get_user_by_username("operator")
    token_resp = auth_service.create_access_token(user)

    # Tamper with the token string
    tampered_token = token_resp.access_token[:-4] + "fake"
    with pytest.raises(HTTPException) as exc_info:
        auth_service.verify_token(tampered_token)
    assert exc_info.value.status_code == 401


def test_expired_jwt_rejected():
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "lead", "role": UserRole.SRE_LEAD.value,
                        "iat": int((now - timedelta(hours=2)).timestamp()),
                        "exp": int((now - timedelta(hours=1)).timestamp())},
                       settings.secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        auth_service.verify_token(token)
    assert exc_info.value.status_code == 401


def test_role_change_revokes_existing_jwt():
    user = auth_service.get_user_by_username("lead")
    token = auth_service.create_access_token(user).access_token
    auth_service.provision_user(
        "lead", "new-lead-credential-2026", UserRole.VIEWER
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_service.resolve_token(token)
    assert exc_info.value.status_code == 401


def test_login_limits_repeated_invalid_passwords(client):
    from src.api.auth_router import login_attempt_limiter

    def login(username, password):
        return client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

    key = ("testclient", "admin")
    login_attempt_limiter.clear(key)
    try:
        for _ in range(5):
            response = login("admin", "WrongPassword")
            assert response.status_code == 401
        blocked = login("admin", "WrongPassword")
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "60"
        assert login("admin", "test-admin-credential-2026").status_code == 429
        viewer_response = login("viewer", "test-viewer-credential-2026")
        assert viewer_response.status_code == 200
    finally:
        login_attempt_limiter.clear(key)
