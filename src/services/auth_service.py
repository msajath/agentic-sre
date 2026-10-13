"""Database-backed credentials and server-side role enforcement."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import List, Optional
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import ValidationError
from src.config import settings
from src.database import SessionLocal, UserModel
from src.models.auth import TokenPayload, TokenResponse, User, UserRole

security_bearer = HTTPBearer(auto_error=False)

class AuthService:
    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

    def initialize(self):
        """Bootstrap explicit credentials; disable legacy demo accounts."""
        with SessionLocal.begin() as session:
            users = session.query(UserModel).all()
            for user in users:
                legacy_password = f"{user.username.capitalize()}Sre@2026"
                if user.username in {"admin", "lead", "operator", "viewer"} and secrets.compare_digest(
                    user.hashed_password, self._hash_password(legacy_password, user.salt)
                ):
                    if user.username == "admin" and settings.bootstrap_admin_password:
                        user.salt = secrets.token_hex(16)
                        user.hashed_password = self._hash_password(settings.bootstrap_admin_password, user.salt)
                        user.is_active = True
                    else:
                        user.is_active = False
            if not users and settings.bootstrap_admin_password:
                session.add(self._user_row("admin", settings.bootstrap_admin_password, UserRole.ADMIN))
            if settings.environment.lower() == "production" and not (
                any(u.is_active and u.role == UserRole.ADMIN.value for u in users)
                or (not users and settings.bootstrap_admin_password)
            ):
                raise ValueError("No active administrator. Set BOOTSTRAP_ADMIN_PASSWORD or provision one with python -m src.manage.")

    def _user_row(self, username: str, password: str, role: UserRole,
                  email: str | None = None, full_name: str | None = None) -> UserModel:
        if not 12 <= len(password) <= 128:
            raise ValueError("Passwords must contain 12 to 128 characters.")
        salt = secrets.token_hex(16)
        user = User(username=username.lower(), email=(email or f"{username}@sre.example.com").lower(),
                    role=role, salt=salt, hashed_password=self._hash_password(password, salt),
                    full_name=full_name or username)
        return UserModel(**user.model_dump(mode="json"))

    def register_viewer(self, username: str, email: str, full_name: str, password: str) -> User:
        """Create a new read-only account; only local administration grants elevated roles."""
        row = self._user_row(username, password, UserRole.VIEWER, email, full_name)
        with SessionLocal.begin() as session:
            session.add(row)
            session.flush()
            return User(username=row.username, email=row.email, role=row.role,
                        hashed_password=row.hashed_password, salt=row.salt,
                        full_name=row.full_name, is_active=row.is_active)

    def provision_user(self, username: str, password: str, role: UserRole) -> None:
        """Local provisioning, also usable to rotate or reactivate accounts."""
        row = self._user_row(username, password, role)
        with SessionLocal.begin() as session:
            session.merge(row)

    def get_user_by_username(self, username: str) -> Optional[User]:
        with SessionLocal() as session:
            row = session.get(UserModel, username.lower())
            if row is None:
                return None
            return User(username=row.username, email=row.email, role=row.role,
                        hashed_password=row.hashed_password, salt=row.salt,
                        full_name=row.full_name, is_active=row.is_active)

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = self.get_user_by_username(username)
        computed = self._hash_password(password, user.salt if user else "invalid-account")
        if user and user.is_active and secrets.compare_digest(computed, user.hashed_password):
            return user
        return None

    def create_access_token(self, user: User) -> TokenResponse:
        now = datetime.now(timezone.utc)
        expiry = timedelta(minutes=settings.token_expire_minutes)
        payload = {"sub": user.username, "role": user.role.value,
                   "exp": int((now + expiry).timestamp()), "iat": int(now.timestamp())}
        return TokenResponse(access_token=jwt.encode(payload, settings.secret_key, algorithm="HS256"),
                             role=user.role, username=user.username, expires_in_sec=int(expiry.total_seconds()))

    def verify_token(self, token_str: str) -> TokenPayload:
        try:
            return TokenPayload(**jwt.decode(token_str, settings.secret_key, algorithms=["HS256"],
                                            options={"require": ["sub", "role", "exp", "iat"]}))
        except (jwt.PyJWTError, ValidationError) as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired token. Please sign in.",
                                headers={"WWW-Authenticate": "Bearer"}) from exc

    def resolve_token(self, token_str: str) -> User:
        payload = self.verify_token(token_str)
        user = self.get_user_by_username(payload.sub)
        if not user or not user.is_active or user.role != payload.role:
            raise HTTPException(status_code=401, detail="Account is inactive or its role has changed.")
        return user

auth_service = AuthService()

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return auth_service.resolve_token(credentials.credentials)

def require_roles(allowed_roles: List[UserRole]):
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your account cannot perform this action.")
        return current_user
    return role_checker
