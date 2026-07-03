"""Escapia HSAPI token acquisition (AGENTS.md Addendum 2; TASKS M4.1).

Spec grounding (Escapia/escapia_openapi3.json):
  operationId ``GenerateToken`` — ``GET /hsapi/auth/token`` with
  ``Authorization: Basic base64(clientId:secret)``. 200 returns schema
  ``TokenCreationResult``: ``{expiration, id, encodedId, authorizationHeaderValue}``.
  ``authorizationHeaderValue`` is the ready-to-send ``Bearer <base64 token>`` header value.

No credentials or token material are ever logged.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

TOKEN_PATH = "/hsapi/auth/token"

# Refresh this long before the reported expiry to avoid using a token that
# dies mid-request.
_REFRESH_SKEW = timedelta(seconds=60)
# If the server omits/garbles `expiration`, assume a conservative lifetime.
_DEFAULT_LIFETIME = timedelta(minutes=30)


class EscapiaAuthError(Exception):
    """Token acquisition failed (never carries credential material)."""


@dataclass
class _CachedToken:
    header_value: str
    expires_at: datetime


def _parse_expiration(raw: str | None) -> datetime:
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            pass
    return datetime.now(UTC) + _DEFAULT_LIFETIME


class EscapiaTokenProvider:
    """Caches the bearer token and refreshes it before expiry."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._cached: _CachedToken | None = None

    def invalidate(self) -> None:
        """Drop the cached token (e.g. after a 401)."""
        self._cached = None

    async def authorization_header(self, http: httpx.AsyncClient) -> str:
        """Return the ``Authorization`` header value, fetching/refreshing as needed."""
        now = datetime.now(UTC)
        if self._cached is not None and now < self._cached.expires_at - _REFRESH_SKEW:
            return self._cached.header_value

        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode("ascii")
        resp = await http.get(
            TOKEN_PATH,
            headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise EscapiaAuthError(f"token endpoint returned HTTP {resp.status_code}")
        data = resp.json()

        # Prefer the pre-built header value; fall back to composing it from the
        # (base64-)encoded token id per the spec's "must be base64 encoded" note.
        header = data.get("authorizationHeaderValue")
        if not header:
            token = data.get("encodedId") or data.get("id")
            if not token:
                raise EscapiaAuthError("token endpoint response had no usable token")
            header = f"Bearer {token}"

        self._cached = _CachedToken(
            header_value=header,
            expires_at=_parse_expiration(data.get("expiration")),
        )
        return self._cached.header_value
