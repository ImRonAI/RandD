"""Escapia PMS integration (AGENTS.md Addendum 2; TASKS M4).

HSAPI REST client + sync jobs. The GraphQL Gateway API is out of v1 scope
(see :mod:`strqc_api.escapia.scheduler` docstring, M4.10).
"""

from .auth import EscapiaAuthError, EscapiaTokenProvider
from .client import EscapiaAPIError, EscapiaClient
from .scheduler import CycleResult, run_forever, run_sync_cycle
from .sync import (
    SyncResult,
    load_housekeeping_status_map,
    push_housekeeping_ready,
    push_work_order,
    sync_owners,
    sync_reservations,
    sync_units,
)

__all__ = [
    "CycleResult",
    "EscapiaAPIError",
    "EscapiaAuthError",
    "EscapiaClient",
    "EscapiaTokenProvider",
    "SyncResult",
    "load_housekeeping_status_map",
    "push_housekeeping_ready",
    "push_work_order",
    "run_forever",
    "run_sync_cycle",
    "sync_owners",
    "sync_reservations",
    "sync_units",
]
