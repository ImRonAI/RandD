"""Reservation delta sync: cursor advance, task upsert, unknown units."""

from __future__ import annotations

import httpx
from strqc_db import repositories

from strqc_api.escapia.sync import sync_reservations

from .conftest import PMC_ID, make_client, token_response

_RESERVATIONS = {
    "RES-1": {
        "nativePMSID": "RES-1",
        "reservationNumber": "1001",
        "unitNativePMSID": "UNIT-014",
        "stayDateRange": {"startDate": "2026-07-10", "endDate": "2026-07-13"},
        "status": "Confirmed",
        "occupancyStatus": "NotOccupied",
    },
    "RES-2": {
        "nativePMSID": "RES-2",
        "reservationNumber": "1002",
        "unitNativePMSID": "UNIT-UNKNOWN",
        "stayDateRange": {"startDate": "2026-07-11", "endDate": "2026-07-14"},
        "status": "Confirmed",
        "occupancyStatus": "NotOccupied",
    },
}


def make_handler(change_batches: dict[int, dict]):
    """Route GetReservationChanges by startVersion + GetReservationById by id."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/hsapi/auth/token"):
            return token_response()
        if path.endswith("/hsapi/GetReservationChanges"):
            start = int(request.url.params["startVersion"])
            batch = change_batches.get(start, {"startVersion": start, "endVersion": start,
                                               "changes": []})
            return httpx.Response(200, json=batch)
        if path.endswith("/hsapi/GetReservationById"):
            res_id = request.url.params["id"]
            return httpx.Response(200, json=_RESERVATIONS[res_id])
        raise AssertionError(f"unexpected path {path}")

    return handler


async def test_delta_creates_tasks_and_advances_cursor(db):
    batches = {
        0: {
            "startVersion": 0,
            "endVersion": 42,
            "changes": [
                {"nativePMSID": "RES-1", "changeType": "Created", "changeTime": "2026-07-01"},
            ],
        },
    }
    async with make_client(make_handler(batches)) as client:
        result = await sync_reservations(db, client, PMC_ID)

    assert result.created == 1 and result.updated == 0
    task = db.execute(
        "SELECT * FROM task WHERE escapia_reservation_native_pms_id = 'RES-1'"
    ).fetchone()
    assert task is not None
    assert task["property_id"] == 1
    assert task["arrival_date"] == "2026-07-10"
    assert task["source_system"] == "ESCAPIA"

    cursor = repositories.get_sync_cursor(db, PMC_ID, "RESERVATIONS")
    assert cursor["start_version"] == 42


async def test_delta_resumes_from_stored_cursor_and_is_idempotent(db):
    repositories.upsert_sync_cursor(db, PMC_ID, "RESERVATIONS", start_version=42)
    batches = {
        42: {
            "startVersion": 42,
            "endVersion": 50,
            "changes": [
                {"nativePMSID": "RES-1", "changeType": "Modified", "changeTime": "2026-07-02"},
            ],
        },
    }
    handler = make_handler(batches)
    async with make_client(handler) as client:
        first = await sync_reservations(db, client, PMC_ID)
    assert first.created == 1  # no existing task yet → created

    # Replay the same batch (cursor manually rewound): must update, not duplicate.
    repositories.upsert_sync_cursor(db, PMC_ID, "RESERVATIONS", start_version=42)
    async with make_client(handler) as client:
        second = await sync_reservations(db, client, PMC_ID)
    assert second.updated == 1 and second.created == 0
    count = db.execute(
        "SELECT COUNT(*) FROM task WHERE escapia_reservation_native_pms_id = 'RES-1'"
    ).fetchone()[0]
    assert count == 1
    assert repositories.get_sync_cursor(db, PMC_ID, "RESERVATIONS")["start_version"] == 50


async def test_unknown_unit_is_skipped_and_collected(db):
    batches = {
        0: {
            "startVersion": 0,
            "endVersion": 10,
            "changes": [
                {"nativePMSID": "RES-2", "changeType": "Created", "changeTime": "2026-07-01"},
            ],
        },
    }
    async with make_client(make_handler(batches)) as client:
        result = await sync_reservations(db, client, PMC_ID)
    assert result.created == 0 and result.skipped == 1
    assert result.unknown_units == ["UNIT-UNKNOWN"]
    # Cursor still advances — the change was seen and consciously skipped.
    assert repositories.get_sync_cursor(db, PMC_ID, "RESERVATIONS")["start_version"] == 10


async def test_deleted_changes_are_skipped_without_detail_fetch(db):
    batches = {
        0: {
            "startVersion": 0,
            "endVersion": 5,
            "changes": [
                {"nativePMSID": "RES-GONE", "changeType": "Deleted", "changeTime": "2026-07-01"},
            ],
        },
    }
    # RES-GONE is not in _RESERVATIONS: a detail fetch would KeyError.
    async with make_client(make_handler(batches)) as client:
        result = await sync_reservations(db, client, PMC_ID)
    assert result.skipped == 1
