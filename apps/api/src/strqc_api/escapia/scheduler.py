"""Minimal asyncio scheduler for Escapia sync jobs (TASKS M4.9).

Built around the spec's one real asymmetry: Reservations is the only delta
feed (``GetReservationChanges``); Units / Owners / Housekeeping have no
changes endpoint and are polled. One cycle = one delta pass + the polls, with
per-resource error isolation so a failing resource never stops the others.

Phase-2 stub (M4.10): the Escapia **GraphQL Gateway API**
(``https://api-gateway.escapia.com/graphql`` — rates, fees, taxes, booking
restrictions/channels, listing content) is explicitly OUT of v1 scope.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import sync
from .client import EscapiaClient

logger = logging.getLogger(__name__)

SyncJob = Callable[[sqlite3.Connection, EscapiaClient, str], Awaitable[Any]]

DEFAULT_INTERVAL_SECONDS = 300.0

#: One delta job (reservations) + the poll-based jobs, in dependency order:
#: units first so reservation/owner lookups can resolve properties.
DEFAULT_JOBS: dict[str, SyncJob] = {
    "units": sync.sync_units,
    "owners": sync.sync_owners,
    "reservations": sync.sync_reservations,
    "housekeeping_status_map": sync.load_housekeeping_status_map,
}


@dataclass
class CycleResult:
    results: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


async def run_sync_cycle(
    conn: sqlite3.Connection,
    client: EscapiaClient,
    pmc_id: str,
    *,
    jobs: dict[str, SyncJob] | None = None,
) -> CycleResult:
    """Run every sync job once; a failure in one resource never stops the rest."""
    cycle = CycleResult()
    for name, job in (jobs if jobs is not None else DEFAULT_JOBS).items():
        try:
            cycle.results[name] = await job(conn, client, pmc_id)
        except Exception as exc:  # noqa: BLE001 — isolation is the point
            # No secrets in logs: exceptions raised here carry only status
            # codes / entity ids, never credentials or token material.
            logger.exception("escapia sync job %r failed", name)
            cycle.errors[name] = f"{type(exc).__name__}: {exc}"
    return cycle


async def run_forever(
    conn: sqlite3.Connection,
    client: EscapiaClient,
    pmc_id: str,
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    jobs: dict[str, SyncJob] | None = None,
    max_cycles: int | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[CycleResult]:
    """Interval-driven loop over :func:`run_sync_cycle`.

    ``max_cycles`` bounds the loop (mainly for tests); ``None`` runs until
    cancelled. Returns the collected cycle results.
    """
    history: list[CycleResult] = []
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        history.append(await run_sync_cycle(conn, client, pmc_id, jobs=jobs))
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        await sleep(interval_seconds)
    return history
