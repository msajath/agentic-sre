"""
Authentication and RBAC Security Service.
Utilizes salted PBKDF2-HMAC-SHA256 for password security and HMAC-SHA256 JWT tokens.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from typing import Dict, List, Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from src.config import settings
from src.models.auth import TokenPayload, TokenResponse, User, UserPublic, UserRole

# HTTP Bearer scheme
security_bearer = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._jwt_secret = settings.secret_key
        self._jwt_algorithm = "HS256"
        self._token_expire_minutes = settings.token_expire_minutes
        self._seed_default_users()

    def _hash_password(self, password: str, salt: str) -> str:
        """Secure PBKDF2 password hashing (100,000 iterations of SHA-256)."""
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        )
        return key.hex()

    def _seed_default_users(self):
        """Seeds enterprise user accounts across the 4 RBAC roles."""
        default_accounts = [
            ("admin", "admin@virtusa-sre.com", "AdminSre@2026", UserRole.ADMIN, "Principal SRE Architect"),
            ("lead", "lead@virtusa-sre.com", "LeadSre@2026", UserRole.SRE_LEAD, "SRE Incident Lead"),
            ("operator", "operator@virtusa-sre.com", "OperatorSre@2026", UserRole.OPERATOR, "SRE Operations Engineer"),
            ("viewer", "viewer@virtusa-sre.com", "ViewerSre@2026", UserRole.VIEWER, "Executive Observability Viewer"),
        ]

        for username, email, pwd, role, full_name in default_accounts:
            salt = secrets.token_hex(16)
            hashed = self._hash_password(pwd, salt)
            self._users[username] = User(
                username=username,
                email=email,
                role=role,
                hashed_password=hashed,
                salt=salt,
                full_name=full_name,
                is_active=True,
            )

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Validates credentials against hashed passwords with constant-time comparison."""
        user = self._users.get(username.lower())
        if not user or not user.is_active:
            return None

        computed_hash = self._hash_password(password, user.salt)
        if secrets.compare_digest(computed_hash, user.hashed_password):
            return user
        return None

    def create_access_token(self, user: User) -> TokenResponse:
        """Issues scoped JWT token with expiration and role claims."""
        now = datetime.now(timezone.utc)
        expires_delta = timedelta(minutes=self._token_expire_minutes)
        exp = int((now + expires_delta).timestamp())
        iat = int(now.timestamp())

        payload = {
            "sub": user.username,
            "role": user.role.value,
            "exp": exp,
            "iat": iat,
        }

        token = jwt.encode(payload, self._jwt_secret, algorithm=self._jwt_algorithm)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            role=user.role,
            username=user.username,
            expires_in_sec=int(expires_delta.total_seconds()),
        )

    def verify_token(self, token_str: str) -> TokenPayload:
        """Decodes and cryptographically validates JWT token."""
        try:
            payload_dict = jwt.decode(
                token_str,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
            )
            return TokenPayload(**payload_dict)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security token has expired. Please re-authenticate.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid cryptographic token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self._users.get(username.lower())


auth_service = AuthService()


# Security Dependencies for FastAPI
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> User:
    """FastAPI dependency: Resolves authenticated user from Bearer JWT header."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = auth_service.verify_token(credentials.credentials)
    user = auth_service.get_user_by_username(payload.sub)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user account not found or deactivated.",
        )
    return user


def require_roles(allowed_roles: List[UserRole]):
    """FastAPI RBAC decorator dependency: Enforces role permissions."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{current_user.role.value}' is unauthorized. Required: {[r.value for r in allowed_roles]}",
            )
        return current_user
    return role_checker
