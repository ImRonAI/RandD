"""Escapia HSAPI HTTP client (AGENTS.md Addendum 2; TASKS M4.1–M4.3).

Every HSAPI call carries the bearer token plus the three required headers
(verified in Escapia/escapia_openapi3.json on every operation's parameters):

  - ``x-homeaway-hasp-api-version``
  - ``x-homeaway-hasp-api-endsystem``  (e.g. ``EscapiaVRS``)
  - ``x-homeaway-hasp-api-pmcid``

Resilience (M4.3): Escapia rate-limits with HTTP 429 but does not publish
limits, so there is deliberately **no hardcoded request budget** — only
generic exponential backoff with jitter on 429/5xx, honoring ``Retry-After``
when present.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, Self

import httpx
from strqc_shared.config import Settings

from .auth import EscapiaTokenProvider

_RETRYABLE_STATUS = frozenset({429}) | frozenset(range(500, 600))


class EscapiaAPIError(Exception):
    """A non-retryable (or retry-exhausted) HSAPI failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EscapiaClient:
    """Async client over ``httpx.AsyncClient`` with injectable transport."""

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        pmc_id: str,
        api_version: str = "1",
        end_system: str = "EscapiaVRS",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        max_attempts: int = 5,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self.pmc_id = pmc_id
        self._api_version = api_version
        self._end_system = end_system
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._sleep = sleep
        self._rng = rng
        self._auth = EscapiaTokenProvider(client_id, client_secret)
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> EscapiaClient:
        return cls(
            base_url=settings.escapia_base_url,
            client_id=settings.escapia_client_id,
            client_secret=settings.escapia_client_secret,
            pmc_id=settings.escapia_pmc_id,
            api_version=settings.escapia_api_version,
            end_system=settings.escapia_end_system,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _backoff_delay(self, attempt: int, retry_after: str | None) -> float:
        """Exponential backoff with jitter; honor ``Retry-After`` when present."""
        if retry_after is not None:
            try:
                return min(self._backoff_cap, max(0.0, float(retry_after)))
            except ValueError:
                pass  # e.g. an HTTP-date — fall through to generic backoff
        delay = min(self._backoff_cap, self._backoff_base * (2**attempt))
        return delay * (0.5 + 0.5 * self._rng())  # jitter in [0.5x, 1.0x]

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Perform one HSAPI call; returns the decoded JSON body (or None)."""
        auth_retried = False
        attempt = 0
        while True:
            headers = {
                "Authorization": await self._auth.authorization_header(self._http),
                "x-homeaway-hasp-api-version": self._api_version,
                "x-homeaway-hasp-api-endsystem": self._end_system,
                "x-homeaway-hasp-api-pmcid": self.pmc_id,
                "Accept": "application/json",
            }
            resp = await self._http.request(method, path, params=params, json=json, headers=headers)

            if resp.status_code == 401 and not auth_retried:
                # Stale token — refresh once immediately, without burning an attempt.
                self._auth.invalidate()
                auth_retried = True
                continue

            if resp.status_code in _RETRYABLE_STATUS:
                if attempt >= self._max_attempts - 1:
                    raise EscapiaAPIError(
                        f"{method} {path} failed with HTTP {resp.status_code} "
                        f"after {self._max_attempts} attempts",
                        status_code=resp.status_code,
                    )
                await self._sleep(self._backoff_delay(attempt, resp.headers.get("Retry-After")))
                attempt += 1
                continue

            if resp.status_code >= 400:
                raise EscapiaAPIError(
                    f"{method} {path} failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
