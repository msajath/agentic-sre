"""
Unit & Security Tests for Authentication, Password Hashing, JWT, and RBAC.
"""

import pytest
from fastapi import HTTPException
from src.models.auth import UserRole
from src.services.auth_service import auth_service


def test_password_authentication():
    """Verify PBKDF2 salted hash validation."""
    # Valid credentials
    user = auth_service.authenticate_user("admin", "AdminSre@2026")
    assert user is not None
    assert user.username == "admin"
    assert user.role == UserRole.ADMIN

    # Invalid password
    assert auth_service.authenticate_user("admin", "WrongPassword") is None

    # Non-existent user
    assert auth_service.authenticate_user("nonexistent", "AdminSre@2026") is None


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
