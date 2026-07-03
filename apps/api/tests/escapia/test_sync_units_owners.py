"""Unit + owner sync: demographics upsert, platform-field preservation, owner links."""

from __future__ import annotations

import httpx
from strqc_db import repositories

from strqc_api.escapia.sync import sync_owners, sync_units

from .conftest import PMC_ID, body_json, make_client, token_response

_UNIT_SUMMARIES = {
    "results": [
        {"nativePMSID": "UNIT-014", "code": "BBL-014", "name": "Grizzly Pines (Escapia)"},
        {"nativePMSID": "UNIT-099", "code": "BBL-099", "name": "Eagle Point"},
    ],
    "totalCount": 2,
    "pageSize": 100,
    "pageNumber": 1,
}

_UNITS = {
    "UNIT-014": {
        "nativePMSID": "UNIT-014",
        "unitCode": "BBL-014",
        "unitName": "Grizzly Pines (Escapia)",
        "address": {"street1": "43210 Moonridge Rd", "city": "Big Bear Lake",
                    "state": "CA", "zip": "92315"},
    },
    "UNIT-099": {
        "nativePMSID": "UNIT-099",
        "unitCode": "BBL-099",
        "unitName": "Eagle Point",
        "address": {"street1": "100 Eagle Point Dr", "city": "Big Bear Lake",
                    "state": "CA", "zip": "92315"},
    },
}


def units_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/hsapi/auth/token"):
        return token_response()
    if path.endswith("/hsapi/SearchUnitSummaries"):
        return httpx.Response(200, json=_UNIT_SUMMARIES)
    if path.endswith("/hsapi/GetUnitsById"):
        ids = body_json(request)
        return httpx.Response(200, json=[_UNITS[i] for i in ids])
    raise AssertionError(f"unexpected path {path}")


async def test_unit_sync_updates_demographics_and_preserves_platform_fields(db):
    before = db.execute("SELECT * FROM property WHERE property_id = 1").fetchone()
    assert before["standing_instructions"] is not None  # seeded platform-only field

    async with make_client(units_handler) as client:
        result = await sync_units(db, client, PMC_ID)

    assert result.updated == 1 and result.created == 1
    after = db.execute("SELECT * FROM property WHERE property_id = 1").fetchone()
    # Demographics refreshed from Escapia:
    assert after["display_name"] == "Grizzly Pines (Escapia)"
    assert after["source_system"] == "ESCAPIA"
    # Platform-only fields untouched (M4.5):
    assert after["standing_instructions"] == before["standing_instructions"]
    assert after["cluster_id"] == before["cluster_id"]
    assert after["qc_assignee_stakeholder_id"] == before["qc_assignee_stakeholder_id"]

    cursor = repositories.get_sync_cursor(db, PMC_ID, "UNITS")
    assert cursor is not None and cursor["last_polled_at"] is not None


async def test_unit_sync_inserts_new_property(db):
    async with make_client(units_handler) as client:
        await sync_units(db, client, PMC_ID)
    new = db.execute("SELECT * FROM property WHERE unit_code = 'BBL-099'").fetchone()
    assert new is not None
    assert new["escapia_unit_native_pms_id"] == "UNIT-099"
    assert new["escapia_pmc_id"] == PMC_ID
    assert new["city"] == "Big Bear Lake"


async def test_unit_sync_adopts_existing_property_by_unit_code(db):
    # Clear the pre-linked Escapia id: sync must match on unit_code and link it.
    db.execute(
        "UPDATE property SET escapia_unit_native_pms_id = NULL, escapia_pmc_id = NULL "
        "WHERE property_id = 1"
    )
    db.commit()
    async with make_client(units_handler) as client:
        await sync_units(db, client, PMC_ID)
    row = db.execute("SELECT * FROM property WHERE unit_code = 'BBL-014'").fetchone()
    assert row["escapia_unit_native_pms_id"] == "UNIT-014"
    count = db.execute("SELECT COUNT(*) FROM property WHERE unit_code = 'BBL-014'").fetchone()[0]
    assert count == 1  # no duplicate created


_OWNERS_PAGE = {
    "results": [
        {
            "nativePMSID": "OWN-7",
            "firstName": "Owen",
            "lastName": "Marsh",
            "emails": [{"address": "owen@escapia.example", "isPrimary": True}],
            "phones": [{"countryCode": "1", "areaCode": "909", "number": "5550199",
                        "isPrimary": True}],
            "ownsUnitNativePMSIDs": ["UNIT-014", "UNIT-027", "UNIT-MISSING"],
        },
    ],
    "totalCount": 1,
    "pageSize": 100,
    "pageNumber": 1,
}


def owners_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/hsapi/auth/token"):
        return token_response()
    if path.endswith("/hsapi/SearchOwners"):
        return httpx.Response(200, json=_OWNERS_PAGE)
    raise AssertionError(f"unexpected path {path}")


async def test_owner_sync_creates_stakeholder_and_property_links(db):
    async with make_client(owners_handler) as client:
        result = await sync_owners(db, client, PMC_ID)

    assert result.created == 1
    owner = db.execute(
        "SELECT * FROM stakeholder WHERE escapia_owner_native_pms_id = 'OWN-7'"
    ).fetchone()
    assert owner["full_name"] == "Owen Marsh"
    assert owner["email"] == "owen@escapia.example"

    links = db.execute(
        """
        SELECT sr.property_id FROM stakeholder_role sr
        JOIN role r ON r.role_id = sr.role_id
        WHERE sr.stakeholder_id = ? AND r.role_key = 'OWNER'
        ORDER BY sr.property_id
        """,
        (owner["stakeholder_id"],),
    ).fetchall()
    assert [row["property_id"] for row in links] == [1, 2]
    assert result.unknown_units == ["UNIT-MISSING"]

    # Second run is idempotent: updates in place, no duplicate links.
    async with make_client(owners_handler) as client:
        again = await sync_owners(db, client, PMC_ID)
    assert again.updated == 1 and again.created == 0
    n_links = db.execute(
        "SELECT COUNT(*) FROM stakeholder_role WHERE stakeholder_id = ?",
        (owner["stakeholder_id"],),
    ).fetchone()[0]
    assert n_links == 2
