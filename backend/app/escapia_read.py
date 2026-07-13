"""Exact, canonical-runtime read-only boundary for Escapia HSAPI v1."""

from __future__ import annotations

from typing import Any, Protocol


class EscapiaHTTPClient(Protocol):
    async def request(self, method: str, path: str, **kwargs: Any) -> Any: ...


class ReadOnlyEscapiaAdapter:
    """Only documented v1 GET operations are accepted; prefix matching is unsafe."""

    READ_ENDPOINTS = frozenset({
        "/hsapi/GetReservationChanges", "/hsapi/SearchReservationSummaries",
        "/hsapi/GetReservationById", "/hsapi/GetReservationByNumber",
        "/hsapi/SearchHousekeepingTasks", "/hsapi/GetHousekeepingStatusList",
        "/hsapi/GetHousekeepingAssigneeList", "/hsapi/GetUnitHousekeepingStatuses",
        "/hsapi/SearchUnitSummaries", "/hsapi/GetUnitById", "/hsapi/GetUnitsById",
        "/hsapi/ListUnitTypes", "/hsapi/ListUnitLocations", "/hsapi/ListUnitFeatureGroups",
        "/hsapi/SearchOwners", "/hsapi/GetOwnerById",
        "/hsapi/SearchGuests", "/hsapi/GetGuestById",
        "/hsapi/SearchWorkOrders", "/hsapi/GetWorkOrder", "/hsapi/GetWorkOrders",
        "/hsapi/GetWorkOrderVendorList", "/hsapi/GetWorkOrderInternalAssigneeList",
        "/hsapi/GetChargeTemplateList",
    })

    def __init__(self, client: EscapiaHTTPClient) -> None:
        self.client = client

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        canonical_path = path.split("?", 1)[0]
        if method.upper() != "GET" or canonical_path not in self.READ_ENDPOINTS:
            raise PermissionError("Escapia integration is read-only in V1 and endpoint is not allowlisted")
        return await self.client.request("GET", path, **kwargs)

    async def search_units(self, *, page_number: int = 1, page_size: int = 100) -> Any:
        return await self.request("GET", "/hsapi/SearchUnitSummaries",
                                  params={"pageNumber": page_number, "pageSize": page_size})

    async def reservation_changes(self, *, start_version: int) -> Any:
        return await self.request("GET", "/hsapi/GetReservationChanges",
                                  params={"startVersion": start_version})

    async def search_owners(self, *, page_number: int = 1, page_size: int = 100) -> Any:
        return await self.request("GET", "/hsapi/SearchOwners",
                                  params={"pageNumber": page_number, "pageSize": page_size})
