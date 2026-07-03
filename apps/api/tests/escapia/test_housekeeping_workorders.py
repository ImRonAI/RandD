"""Housekeeping status map load + guest-ready write-back, and work order push."""

from __future__ import annotations

import httpx
import pytest
from strqc_db import repositories

from strqc_api.escapia.sync import (
    load_housekeeping_status_map,
    push_housekeeping_ready,
    push_work_order,
)

from .conftest import PMC_ID, body_json, make_client, token_response

_STATUS_LIST = [
    {"nativePMSID": "HS-CLEAN", "nativeStatusId": 11, "name": "Clean",
     "abbreviation": "C", "isDefaultOnCheckIn": True, "isDefaultOnCheckOut": False},
    {"nativePMSID": "HS-DIRTY", "nativeStatusId": 12, "name": "Dirty",
     "abbreviation": "D", "isDefaultOnCheckIn": False, "isDefaultOnCheckOut": True},
    {"nativePMSID": "HS-INSP", "nativeStatusId": 13, "name": "Inspected",
     "abbreviation": "I", "isDefaultOnCheckIn": False, "isDefaultOnCheckOut": False},
]


class HousekeepingHandler:
    def __init__(self):
        self.saved: list[tuple[str, dict]] = []  # (nativeUnitId, body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/hsapi/auth/token"):
            return token_response()
        if path.endswith("/hsapi/GetHousekeepingStatusList"):
            return httpx.Response(200, json=_STATUS_LIST)
        if path.endswith("/hsapi/SaveUnitHousekeepingStatus"):
            self.saved.append((request.url.params["nativeUnitId"], body_json(request)))
            return httpx.Response(200, json=True)
        raise AssertionError(f"unexpected path {path}")


async def test_status_map_loaded_from_pmc_lookup(db):
    handler = HousekeepingHandler()
    async with make_client(handler) as client:
        written = await load_housekeeping_status_map(db, client, PMC_ID)
    assert written == 2  # DONE ← isDefaultOnCheckIn, CLN ← isDefaultOnCheckOut

    rows = db.execute(
        """
        SELECT sd.stage_key, m.escapia_clean_status_id, m.escapia_status_label
        FROM housekeeping_status_map m
        JOIN stage_definition sd ON sd.stage_definition_id = m.stage_definition_id
        WHERE m.pmc_id = ? ORDER BY sd.stage_key
        """,
        (PMC_ID,),
    ).fetchall()
    by_stage = {r["stage_key"]: r for r in rows}
    assert by_stage["DONE"]["escapia_clean_status_id"] == "HS-CLEAN"
    assert by_stage["CLN"]["escapia_clean_status_id"] == "HS-DIRTY"
    assert repositories.get_sync_cursor(db, PMC_ID, "HOUSEKEEPING")["last_polled_at"] is not None


async def test_status_map_supports_operator_overrides(db):
    handler = HousekeepingHandler()
    async with make_client(handler) as client:
        await load_housekeeping_status_map(
            db, client, PMC_ID, stage_to_status_name={"DONE": "inspected"}
        )
    row = db.execute(
        """
        SELECT m.escapia_clean_status_id FROM housekeeping_status_map m
        JOIN stage_definition sd ON sd.stage_definition_id = m.stage_definition_id
        WHERE m.pmc_id = ? AND sd.stage_key = 'DONE'
        """,
        (PMC_ID,),
    ).fetchone()
    assert row["escapia_clean_status_id"] == "HS-INSP"


async def test_push_ready_uses_mapped_status(db):
    handler = HousekeepingHandler()
    async with make_client(handler) as client:
        await load_housekeeping_status_map(db, client, PMC_ID)
        ok = await push_housekeeping_ready(db, client, PMC_ID, task_id=1)  # property 1 → UNIT-014
    assert ok is True
    native_unit_id, body = handler.saved[0]
    assert native_unit_id == "UNIT-014"
    assert body["nativePMSID"] == "HS-CLEAN"
    assert body["name"] == "Clean"


async def test_push_ready_fails_without_status_map(db):
    handler = HousekeepingHandler()
    async with make_client(handler) as client:
        with pytest.raises(LookupError, match="load_housekeeping_status_map"):
            await push_housekeeping_ready(db, client, PMC_ID, task_id=1)
    assert handler.saved == []  # nothing was hardcoded or sent


class WorkOrderHandler:
    def __init__(self):
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/hsapi/auth/token"):
            return token_response()
        if path.endswith("/hsapi/SaveWorkOrder"):
            body = body_json(request)
            self.bodies.append(body)
            return httpx.Response(200, json={**body, "nativePMSID": "WO-555"})
        raise AssertionError(f"unexpected path {path}")


async def test_work_order_push_maps_priority_and_stores_native_id(db):
    wo_id = repositories.create_work_order(
        db, property_id=1, task_id=1, details="Hot tub heater dead — 68°F", priority="URGENT"
    )
    handler = WorkOrderHandler()
    async with make_client(handler) as client:
        native_id = await push_work_order(db, client, PMC_ID, wo_id)

    assert native_id == "WO-555"
    body = handler.bodies[0]
    assert body["priority"] == "Urgent"  # spec enum: Urgent|High|Medium|Low|None
    assert body["status"] == "Pending"
    assert body["unit"]["nativePMSID"] == "UNIT-014"
    assert body["description"] == "Hot tub heater dead — 68°F"

    row = db.execute("SELECT * FROM work_order WHERE work_order_id = ?", (wo_id,)).fetchone()
    assert row["escapia_work_order_native_pms_id"] == "WO-555"

    # Re-push includes the native id so Escapia updates instead of duplicating.
    async with make_client(handler) as client:
        await push_work_order(db, client, PMC_ID, wo_id)
    assert handler.bodies[1]["nativePMSID"] == "WO-555"


async def test_work_order_push_requires_escapia_linked_property(db):
    wo_id = repositories.create_work_order(db, property_id=3, task_id=None, details="x")
    handler = WorkOrderHandler()
    async with make_client(handler) as client:
        with pytest.raises(LookupError, match="escapia_unit_native_pms_id"):
            await push_work_order(db, client, PMC_ID, wo_id)
