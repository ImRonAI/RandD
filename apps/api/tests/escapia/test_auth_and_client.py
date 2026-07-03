"""Auth token caching/refresh + client header injection and 429/5xx backoff."""

from __future__ import annotations

import httpx
import pytest

from strqc_api.escapia.client import EscapiaAPIError

from .conftest import make_client, token_response


class Recorder:
    """Routes /hsapi/auth/token and one data path; records requests."""

    def __init__(self, data_response_factory=None, token_lifetime: int = 3600):
        self.token_calls = 0
        self.data_requests: list[httpx.Request] = []
        self.token_lifetime = token_lifetime
        self._data = data_response_factory or (lambda req: httpx.Response(200, json={"ok": True}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hsapi/auth/token"):
            self.token_calls += 1
            return token_response(
                lifetime_seconds=self.token_lifetime, token=f"tok-{self.token_calls}"
            )
        self.data_requests.append(request)
        return self._data(request)


async def test_token_is_cached_across_requests():
    rec = Recorder()
    async with make_client(rec) as client:
        await client.request("GET", "/hsapi/GetHousekeepingStatusList")
        await client.request("GET", "/hsapi/GetHousekeepingStatusList")
    assert rec.token_calls == 1
    assert all(r.headers["Authorization"] == "Bearer tok-1" for r in rec.data_requests)


async def test_token_refreshed_before_expiry():
    # Lifetime shorter than the 60s refresh skew → every call re-fetches.
    rec = Recorder(token_lifetime=10)
    async with make_client(rec) as client:
        await client.request("GET", "/hsapi/GetHousekeepingStatusList")
        await client.request("GET", "/hsapi/GetHousekeepingStatusList")
    assert rec.token_calls == 2
    assert rec.data_requests[-1].headers["Authorization"] == "Bearer tok-2"


async def test_401_invalidates_token_and_retries_once():
    seen = {"n": 0}

    def data(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"ok": True})

    rec = Recorder(data)
    async with make_client(rec) as client:
        assert await client.request("GET", "/hsapi/GetHousekeepingStatusList") == {"ok": True}
    assert rec.token_calls == 2  # refreshed after the 401


async def test_required_headers_injected_on_every_call():
    rec = Recorder()
    async with make_client(rec) as client:
        await client.request("GET", "/hsapi/GetReservationChanges", params={"startVersion": 0})
    req = rec.data_requests[0]
    # Exact header names verified against escapia_openapi3.json parameters.
    assert req.headers["x-homeaway-hasp-api-version"] == "10"
    assert req.headers["x-homeaway-hasp-api-endsystem"] == "EscapiaVRS"
    assert req.headers["x-homeaway-hasp-api-pmcid"] == "1020"
    assert req.headers["Authorization"].startswith("Bearer ")


async def test_429_retries_with_exponential_backoff():
    responses = [429, 429, 200]
    sleeps: list[float] = []

    def data(request: httpx.Request) -> httpx.Response:
        code = responses.pop(0)
        return httpx.Response(code, json={"ok": True} if code == 200 else None)

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    rec = Recorder(data)
    async with make_client(rec, sleep=record_sleep, backoff_base=1.0) as client:
        assert await client.request("GET", "/hsapi/GetHousekeepingStatusList") == {"ok": True}
    # rng fixed at 1.0 → delay = base * 2**attempt exactly.
    assert sleeps == [1.0, 2.0]


async def test_retry_after_header_is_honored():
    responses = [429, 200]
    sleeps: list[float] = []

    def data(request: httpx.Request) -> httpx.Response:
        code = responses.pop(0)
        if code == 429:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"ok": True})

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    rec = Recorder(data)
    async with make_client(rec, sleep=record_sleep) as client:
        await client.request("GET", "/hsapi/GetHousekeepingStatusList")
    assert sleeps == [7.0]


async def test_retry_exhaustion_raises():
    rec = Recorder(lambda req: httpx.Response(503))
    async with make_client(rec, max_attempts=3) as client:
        with pytest.raises(EscapiaAPIError) as excinfo:
            await client.request("GET", "/hsapi/GetHousekeepingStatusList")
    assert excinfo.value.status_code == 503
    assert len(rec.data_requests) == 3


async def test_backoff_delay_is_capped():
    rec = Recorder(lambda req: httpx.Response(200, json={}))
    async with make_client(rec, backoff_base=10.0, backoff_cap=30.0) as client:
        assert client._backoff_delay(4, None) == 30.0  # 10 * 2**4 = 160 → capped
        assert client._backoff_delay(0, "999") == 30.0  # Retry-After capped too
