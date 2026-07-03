"""Typed wrappers for the HSAPI operations consumed in v1 (TASKS M4.2, M4.4–M4.8).

Each wrapper cites the ``operationId`` from Escapia/escapia_openapi3.json.
Models are deliberately thin — only the fields this platform consumes are
transcribed (per M4.2: the OpenAPI spec is the contract, don't hand-copy schemas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import EscapiaClient

# ── models (subset of spec schemas) ──────────────────────────────────────────


@dataclass
class EntityChange:
    """Spec schema ``EntityChange`` — {nativePMSID, changeType, changeTime}."""

    native_pms_id: str
    change_type: str
    change_time: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EntityChange:
        return cls(
            native_pms_id=str(data.get("nativePMSID", "")),
            change_type=str(data.get("changeType", "")),
            change_time=data.get("changeTime"),
        )


@dataclass
class ChangeList:
    """Spec schema ``ChangeList`` — {startVersion, endVersion, changes[]}."""

    start_version: int
    end_version: int
    changes: list[EntityChange] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ChangeList:
        return cls(
            start_version=int(data.get("startVersion") or 0),
            end_version=int(data.get("endVersion") or 0),
            changes=[EntityChange.from_json(c) for c in data.get("changes") or []],
        )


@dataclass
class Reservation:
    """Subset of spec schema ``Reservation``."""

    native_pms_id: str
    reservation_number: str | None
    unit_native_pms_id: str | None
    arrival_date: str | None  # stayDateRange.startDate
    departure_date: str | None  # stayDateRange.endDate
    status: str | None
    occupancy_status: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Reservation:
        stay = data.get("stayDateRange") or {}
        return cls(
            native_pms_id=str(data.get("nativePMSID", "")),
            reservation_number=data.get("reservationNumber"),
            unit_native_pms_id=data.get("unitNativePMSID"),
            arrival_date=stay.get("startDate"),
            departure_date=stay.get("endDate"),
            status=data.get("status"),
            occupancy_status=data.get("occupancyStatus"),
        )


@dataclass
class UnitSummary:
    """Subset of spec schema ``UnitSummary``."""

    native_pms_id: str
    code: str | None
    name: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UnitSummary:
        return cls(
            native_pms_id=str(data.get("nativePMSID", "")),
            code=data.get("code"),
            name=data.get("name"),
        )


@dataclass
class PagedUnitSummaries:
    """Subset of spec schema ``PagedSearchResults_UnitSummary``."""

    results: list[UnitSummary]
    total_count: int
    page_number: int
    page_size: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PagedUnitSummaries:
        return cls(
            results=[UnitSummary.from_json(u) for u in data.get("results") or []],
            total_count=int(data.get("totalCount") or 0),
            page_number=int(data.get("pageNumber") or 1),
            page_size=int(data.get("pageSize") or 0),
        )


@dataclass
class Unit:
    """Subset of spec schema ``Unit`` (the 51-field property master record)."""

    native_pms_id: str
    unit_code: str | None
    unit_name: str | None
    address_line_1: str | None  # address.street1
    city: str | None
    state_province: str | None  # address.state (falls back to province)
    postal_code: str | None  # address.zip

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Unit:
        addr = data.get("address") or {}
        return cls(
            native_pms_id=str(data.get("nativePMSID", "")),
            unit_code=data.get("unitCode"),
            unit_name=data.get("unitName"),
            address_line_1=addr.get("street1"),
            city=addr.get("city"),
            state_province=addr.get("state") or addr.get("province"),
            postal_code=addr.get("zip"),
        )


def _primary(items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not items:
        return None
    for it in items:
        if it.get("isPrimary"):
            return it
    return items[0]


@dataclass
class Owner:
    """Subset of spec schema ``Owner`` — note ``ownsUnitNativePMSIDs`` gives the
    owner↔unit linkage directly (AGENTS.md Addendum 2)."""

    native_pms_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    owns_unit_native_pms_ids: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or self.native_pms_id

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Owner:
        email = _primary(data.get("emails"))
        phone = _primary(data.get("phones"))
        phone_str = None
        if phone:
            parts = [phone.get("countryCode"), phone.get("areaCode"), phone.get("number")]
            phone_str = "-".join(p for p in parts if p) or None
        return cls(
            native_pms_id=str(data.get("nativePMSID", "")),
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
            email=email.get("address") if email else None,
            phone=phone_str,
            owns_unit_native_pms_ids=[str(u) for u in data.get("ownsUnitNativePMSIDs") or []],
        )


@dataclass
class HousekeepingStatus:
    """Spec schema ``HousekeepingStatus`` — PMC-configurable lookup, never hardcode."""

    native_pms_id: str
    native_status_id: int | None
    name: str | None
    abbreviation: str | None
    is_default_on_check_in: bool
    is_default_on_check_out: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> HousekeepingStatus:
        return cls(
            native_pms_id=str(data.get("nativePMSID") or data.get("nativeStatusId") or ""),
            native_status_id=data.get("nativeStatusId"),
            name=data.get("name"),
            abbreviation=data.get("abbreviation"),
            is_default_on_check_in=bool(data.get("isDefaultOnCheckIn")),
            is_default_on_check_out=bool(data.get("isDefaultOnCheckOut")),
        )


# ── typed endpoint wrappers ──────────────────────────────────────────────────


# operationId: GetReservationChanges — GET /hsapi/GetReservationChanges?startVersion=<int64>
# The ONLY delta endpoint in the spec (start at 0; advance to returned endVersion).
async def get_reservation_changes(client: EscapiaClient, *, start_version: int) -> ChangeList:
    data = await client.request(
        "GET", "/hsapi/GetReservationChanges", params={"startVersion": start_version}
    )
    return ChangeList.from_json(data or {})


# operationId: GetReservationById — GET /hsapi/GetReservationById?id=<nativePMSID>
# Per the spec: "specified by the reservation's NativePMSID".
async def get_reservation_by_id(client: EscapiaClient, native_pms_id: str) -> Reservation:
    data = await client.request("GET", "/hsapi/GetReservationById", params={"id": native_pms_id})
    return Reservation.from_json(data or {})


# operationId: SearchUnitSummaries — POST /hsapi/SearchUnitSummaries
# Body: PagedSearchSpecification_UnitSearchSpecification {specification, pageSize, pageNumber}.
async def search_unit_summaries(
    client: EscapiaClient,
    *,
    page_number: int = 1,
    page_size: int = 100,
    return_inactive_units: bool = False,
) -> PagedUnitSummaries:
    body = {
        "specification": {
            "returnUnavailableUnits": True,
            "returnInactiveUnits": return_inactive_units,
        },
        "pageSize": page_size,
        "pageNumber": page_number,
    }
    data = await client.request("POST", "/hsapi/SearchUnitSummaries", json=body)
    return PagedUnitSummaries.from_json(data or {})


# operationId: GetUnitsById — POST /hsapi/GetUnitsById (body: array of nativePMSID strings).
async def get_units_by_id(client: EscapiaClient, native_pms_ids: list[str]) -> list[Unit]:
    data = await client.request("POST", "/hsapi/GetUnitsById", json=list(native_pms_ids))
    return [Unit.from_json(u) for u in data or []]


# operationId: SearchOwners — POST /hsapi/SearchOwners
# Body: PagedSearchSpecification_OwnerSearchSpecification.
async def search_owners(
    client: EscapiaClient, *, page_number: int = 1, page_size: int = 100
) -> tuple[list[Owner], int]:
    body = {"specification": {}, "pageSize": page_size, "pageNumber": page_number}
    data = await client.request("POST", "/hsapi/SearchOwners", json=body)
    data = data or {}
    owners = [Owner.from_json(o) for o in data.get("results") or []]
    return owners, int(data.get("totalCount") or 0)


# operationId: GetHousekeepingStatusList — GET /hsapi/GetHousekeepingStatusList
# Returns array<HousekeepingStatus>; values are PMC-configurable (never hardcode).
async def get_housekeeping_status_list(client: EscapiaClient) -> list[HousekeepingStatus]:
    data = await client.request("GET", "/hsapi/GetHousekeepingStatusList")
    return [HousekeepingStatus.from_json(s) for s in data or []]


# operationId: SaveUnitHousekeepingStatus — PUT /hsapi/SaveUnitHousekeepingStatus?nativeUnitId=<id>
# Body: UnitHousekeepingStatusType {name, id, pmcid, nativePMSID}; 200 returns a boolean.
async def save_unit_housekeeping_status(
    client: EscapiaClient,
    *,
    native_unit_id: str,
    status_native_pms_id: str,
    status_name: str | None = None,
) -> bool:
    body: dict[str, Any] = {"nativePMSID": status_native_pms_id}
    if status_name:
        body["name"] = status_name
    data = await client.request(
        "PUT",
        "/hsapi/SaveUnitHousekeepingStatus",
        params={"nativeUnitId": native_unit_id},
        json=body,
    )
    return bool(data)


# operationId: SaveWorkOrder — PUT /hsapi/SaveWorkOrder (body + 200 response: WorkOrder).
# priority enum per spec: Urgent | High | Medium | Low | None.
# status enum per spec: Pending | Started | Completed | Assigned | Entered | Approved
#                       | Scheduled | Posted.
async def save_work_order(client: EscapiaClient, work_order: dict[str, Any]) -> dict[str, Any]:
    data = await client.request("PUT", "/hsapi/SaveWorkOrder", json=work_order)
    return data or {}
