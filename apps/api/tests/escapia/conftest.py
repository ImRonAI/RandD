"""Shared fixtures for Escapia integration tests. No real network — all HTTP
goes through httpx.MockTransport with canned JSON matching the OpenAPI shapes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from strqc_db.connection import connect
from strqc_db.migrate import migrate
from strqc_db.seed import seed

from strqc_api.escapia.client import EscapiaClient

PMC_ID = "1020"
BASE_URL = "https://hsapi.escapia.com/dragomanadapter"


def token_response(*, lifetime_seconds: int = 3600, token: str = "tok-1") -> httpx.Response:
    """Canned TokenCreationResult per the spec schema."""
    exp = (datetime.now(UTC) + timedelta(seconds=lifetime_seconds)).isoformat()
    return httpx.Response(
        200,
        json={
            "expiration": exp,
            "id": token,
            "encodedId": token,
            "authorizationHeaderValue": f"Bearer {token}",
        },
    )


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], **overrides: Any
) -> EscapiaClient:
    kwargs: dict[str, Any] = dict(
        base_url=BASE_URL,
        client_id="client-id",
        client_secret="client-secret",
        pmc_id=PMC_ID,
        api_version="10",
        end_system="EscapiaVRS",
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        rng=lambda: 1.0,  # deterministic jitter (full delay)
    )
    kwargs.update(overrides)
    return EscapiaClient(**kwargs)


async def _no_sleep(_delay: float) -> None:
    return None


def body_json(request: httpx.Request) -> Any:
    return json.loads(request.content.decode()) if request.content else None


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    """Migrated + seeded dev DB with Escapia unit ids on the seed properties."""
    path = tmp_path / "test.sqlite"
    migrate(path)
    seed(path)
    conn = connect(path)
    conn.execute(
        "UPDATE property SET escapia_unit_native_pms_id = 'UNIT-014', escapia_pmc_id = ? "
        "WHERE property_id = 1",
        (PMC_ID,),
    )
    conn.execute(
        "UPDATE property SET escapia_unit_native_pms_id = 'UNIT-027', escapia_pmc_id = ? "
        "WHERE property_id = 2",
        (PMC_ID,),
    )
    conn.commit()
    yield conn
    conn.close()
