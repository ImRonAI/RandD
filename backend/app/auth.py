"""Authentication: password hashing, cookie sessions, short-lived WS tokens.

Stateless verification against ``STRQC_SESSION_SECRET`` — no session store, no
external identity provider. Two token kinds:

* **Session** — signed, HTTP-only cookie carrying
  ``{user_id, tenant_id, is_platform_admin, exp}``; ~12h lifetime. Read by the
  ``current_user`` dependency on every ``/api/*`` route.
* **WS token** — a separate short-lived (~60s) JWT minted by an authed HTTP call
  and passed as ``/ws?token=…`` (browsers cannot set WS headers).

Both are JWTs signed HS256 with the same secret, distinguished by a ``typ``
claim so a WS token can never be replayed as a session cookie and vice-versa.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 12 * 60 * 60  # 12h
WS_TOKEN_TTL_SECONDS = 60           # short-lived, single-use at accept()
_ALGO = "HS256"
_TYP_SESSION = "session"
_TYP_WS = "ws"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def cookie_name() -> str:
    return os.getenv("STRQC_AUTH_COOKIE_NAME", "strqc_session")


def _secret() -> str:
    secret = os.getenv("STRQC_SESSION_SECRET", "")
    if not secret:
        # Fail loud: never silently sign with an empty key.
        raise RuntimeError("STRQC_SESSION_SECRET is not set")
    return secret


def _is_prod() -> bool:
    # Secure cookies in prod (HTTPS); relaxed for local http dev.
    return os.getenv("STRQC_ENV", "").lower() in {"prod", "production"} or bool(
        os.getenv("STRQC_FORCE_SECURE_COOKIE")
    )


def _db_path() -> Path:
    raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token mint / verify
# ---------------------------------------------------------------------------

def create_session_token(user_id: int, tenant_id: Optional[int], is_platform_admin: bool) -> str:
    now = int(time.time())
    payload = {
        "typ": _TYP_SESSION,
        "user_id": int(user_id),
        "tenant_id": None if tenant_id is None else int(tenant_id),
        "is_platform_admin": bool(is_platform_admin),
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def create_ws_token(user_id: int, tenant_id: Optional[int], is_platform_admin: bool) -> str:
    now = int(time.time())
    payload = {
        "typ": _TYP_WS,
        "user_id": int(user_id),
        "tenant_id": None if tenant_id is None else int(tenant_id),
        "is_platform_admin": bool(is_platform_admin),
        "iat": now,
        "exp": now + WS_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def _decode(token: str, expected_typ: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("typ") != expected_typ:
        raise ValueError("wrong token type")
    return payload


def verify_ws_token(token: str) -> Dict[str, Any]:
    """Validate a WS token; returns the claims. Raises ValueError on failure."""
    return _decode(token, _TYP_WS)


def set_session_cookie(response, token: str) -> None:
    """Attach the signed HTTP-only session cookie to a FastAPI response."""
    response.set_cookie(
        key=cookie_name(),
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_is_prod(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=cookie_name(), path="/")


# ---------------------------------------------------------------------------
# User loading
# ---------------------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, tenant_id, email, password_hash, is_platform_admin,
                   stakeholder_id, is_active
              FROM app_user
             WHERE email = ?
            """,
            (email,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, tenant_id, email, password_hash, is_platform_admin,
                   stakeholder_id, is_active
              FROM app_user
             WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_tenant_by_id(tenant_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if tenant_id is None:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT tenant_id, name, slug, is_active FROM tenant WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def resolve_current_user(token: Optional[str]) -> Dict[str, Any]:
    """Pure verification used by both the HTTP dependency and tests.

    Returns ``{user_id, tenant_id, is_platform_admin}``. Raises 401 on any
    failure (missing/expired/tampered token, unknown or inactive user).
    """
    if not token:
        raise _unauthorized()
    try:
        payload = _decode(token, _TYP_SESSION)
    except ValueError as exc:
        raise _unauthorized(str(exc))
    user = get_user_by_id(int(payload["user_id"]))
    if not user or not user.get("is_active"):
        raise _unauthorized("user inactive or missing")
    return {
        "user_id": user["user_id"],
        "tenant_id": user["tenant_id"],
        "is_platform_admin": bool(user["is_platform_admin"]),
    }


async def current_user(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: verify the session cookie and load the user."""
    token = request.cookies.get(cookie_name())
    return resolve_current_user(token)


async def require_platform_admin(
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    """FastAPI dependency: 403 unless the caller is a platform super-admin."""
    if not user.get("is_platform_admin"):
        raise _forbidden("platform admin required")
    return user
