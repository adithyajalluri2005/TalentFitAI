"""Authentication for the Recruitment Assistant API.

Accounts are seeded from environment variables rather than a database table.
The free hosting tier has no persistent disk, so a users table would be wiped on
every restart and self-registered accounts would silently disappear. Seeding from
env keeps credentials stable across redeploys.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------
# Configuration
# ---------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

# A generated secret means every restart invalidates outstanding tokens, which
# on a free tier that sleeps means users get logged out unpredictably. Set
# JWT_SECRET in the environment for anything real.
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    logger.warning(
        "JWT_SECRET is not set; generated an ephemeral one. "
        "Tokens will be invalidated on every restart."
    )

Role = Literal["user", "admin"]


class User(BaseModel):
    username: str
    role: Role


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    username: str
    expires_in: int


# ---------------------------
# Password hashing
# ---------------------------
def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())


def verify_password(plain: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed)
    except (ValueError, TypeError):
        return False


# ---------------------------
# Seeded accounts
# ---------------------------
def _build_users() -> dict[str, dict]:
    """Hash the configured credentials once at import."""
    users: dict[str, dict] = {}

    admin_user = os.getenv("ADMIN_USERNAME", "admin").strip()
    admin_pass = os.getenv("ADMIN_PASSWORD", "").strip()
    cand_user = os.getenv("USER_USERNAME", "user").strip()
    cand_pass = os.getenv("USER_PASSWORD", "").strip()

    # Dev-only fallbacks. Refusing to start without them would make local runs
    # painful, so warn loudly instead.
    if not admin_pass:
        admin_pass = "adminpass"
        logger.warning("ADMIN_PASSWORD not set; using an insecure development default.")
    if not cand_pass:
        cand_pass = "userpass"
        logger.warning("USER_PASSWORD not set; using an insecure development default.")

    users[admin_user.lower()] = {
        "username": admin_user,
        "role": "admin",
        "password_hash": hash_password(admin_pass),
    }
    users[cand_user.lower()] = {
        "username": cand_user,
        "role": "user",
        "password_hash": hash_password(cand_pass),
    }
    return users


_USERS = _build_users()


def authenticate(username: str, password: str) -> Optional[User]:
    record = _USERS.get((username or "").strip().lower())
    if record is None:
        # Hash anyway so a missing user and a wrong password take similar time.
        verify_password(password, hash_password("dummy"))
        return None
    if not verify_password(password, record["password_hash"]):
        return None
    return User(username=record["username"], role=record["role"])


# ---------------------------
# Tokens
# ---------------------------
def create_access_token(user: User) -> tuple[str, int]:
    expires_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_seconds),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM), expires_seconds


# ---------------------------
# Dependencies
# ---------------------------
# auto_error=False so a missing header yields our own 401 with a WWW-Authenticate
# challenge rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise _UNAUTHORIZED

    username = payload.get("sub")
    role = payload.get("role")
    if not username or role not in ("user", "admin"):
        raise _UNAUTHORIZED
    return User(username=username, role=role)


def require_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current
