"""
backend/services/auth_service.py
=================================
Authentication: password check, JWT creation, FastAPI Depends() guards.

Tokens are Bearer JWTs signed with JWT_SECRET_KEY (env var).
Set a strong secret in production — the default is dev-only.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from backend.models.database import get_user

# ── Config ─────────────────────────────────────────────────────────────────────
SECRET_KEY  = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM   = "HS256"
TOKEN_TTL_H = 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_access_token(username: str, role: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_H)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> dict | None:
    """Returns {"username": ..., "role": ...} or None on failure."""
    row = get_user(username)
    if not row:
        return None
    if row["password"] != _hash(password):
        return None
    return {"username": row["username"], "role": row["role"]}


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Inject into any route that requires authentication."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role     = payload.get("role")
        if not username or not role:
            raise exc
    except JWTError:
        raise exc
    return {"username": username, "role": role}


def require_role(required_role: str):
    """
    Role-guard factory.  Usage:
        _user = Depends(require_role("inspector"))
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{required_role}' role.",
            )
        return user
    return _check
