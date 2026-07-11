from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.vantage.context import TenantContext
from app.vantage.google_day import (
    ExpiredSyncToken,
    GoogleCalendarService,
    GoogleIntegrationError,
    GoogleNavigationService,
    GooglePlacesService,
)


CTX = TenantContext("user-a", "org-a", frozenset({"INSPECTOR"}))


class Authorization:
    def calendar_connection(self, context: TenantContext) -> dict[str, Any] | None:
        return {"calendarId": "primary", "organizationId": context.organization_id, "status": "connected"}

    def authorize_calendar_link(self, context: TenantContext, properties: dict[str, str]) -> dict[str, Any] | None:
        if properties.get("vantageOrgId") != context.organization_id or properties.get("vantageTaskId") != "task-a":
            return None
        return {"taskId": "task-a", "homeId": "home-a"}

    def day_stops(self, context: TenantContext, day: date) -> list[dict[str, Any]]:
        assert context.organization_id == "org-a"
        return [
            {"taskId": "task-a", "homeId": "home-a", "latitude": 34.1, "longitude": -117.1, "placeId": "place-a"},
            {"taskId": "task-b", "homeId": "home-b", "latitude": 34.2, "longitude": -117.2, "placeId": "place-b"},
            {"taskId": "task-c", "homeId": "home-c", "latitude": 34.3, "longitude": -117.3, "placeId": "place-c"},
        ]

    def authorize_task_ids(self, context: TenantContext, day: date, task_ids: list[str]) -> list[dict[str, Any]]:
        return [x for x in self.day_stops(context, day) if x["taskId"] in task_ids]


class Calendar:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.expire_once = False

    def list_events(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.expire_once and kwargs["sync_token"]:
            self.expire_once = False
            raise ExpiredSyncToken()
        if not kwargs["page_token"]:
            return {"items": [{"id": "event-a", "start": {"dateTime": "2026-07-11T09:00:00-07:00"},
                                "extendedProperties": {"private": {"vantageOrgId": "org-a", "vantageTaskId": "task-a"}}}],
                    "nextPageToken": "page-2"}
        return {"items": [{"id": "foreign", "start": {"date": "2026-07-11"},
                            "extendedProperties": {"private": {"vantageOrgId": "org-b", "vantageTaskId": "task-z"}}}],
                "nextSyncToken": "sync-next"}


def test_calendar_paginates_stores_sync_token_and_reauthorizes_private_links() -> None:
    client = Calendar()
    service = GoogleCalendarService(client, Authorization())
    result = service.sync(CTX)
    assert result["changed"] == 2 and result["syncTokenStored"]
    assert client.calls[1]["page_token"] == "page-2"
    events = service.day(CTX, date(2026, 7, 11))["events"]
    by_id = {event["id"]: event for event in events}
    assert by_id["event-a"]["vantageLink"] == {"taskId": "task-a", "homeId": "home-a"}
    assert "foreign" not in by_id


def test_calendar_410_clears_and_runs_full_sync() -> None:
    client = Calendar()
    service = GoogleCalendarService(client, Authorization())
    service.sync(CTX)
    client.expire_once = True
    result = service.sync(CTX)
    assert result["recoveredFromExpiredToken"] is True
    assert any(call["sync_token"] is None for call in client.calls[-2:])


class Places:
    def __init__(self) -> None: self.details_call: dict[str, Any] = {}
    def autocomplete(self, **kwargs: Any) -> list[dict[str, Any]]: return [{"placeId": "p", "text": kwargs["text"]}]
    def details(self, **kwargs: Any) -> dict[str, Any]:
        self.details_call = kwargs
        return {"id": "p", "displayName": {"text": "Cabin"}, "formattedAddress": "1 Pine Rd",
                "location": {"latitude": 34.2, "longitude": -117.2}, "ignored": "not returned"}


def test_places_uses_same_session_token_and_minimal_details_fields() -> None:
    client = Places()
    service = GooglePlacesService(client)
    assert service.autocomplete("1 Pine", "session-1")[0]["placeId"] == "p"
    result = service.resolve("p", "session-1")
    assert client.details_call["session_token"] == "session-1"
    assert client.details_call["fields"] == ("id", "displayName", "formattedAddress", "location")
    assert result == {"placeId": "p", "displayName": "Cabin", "formattedAddress": "1 Pine Rd",
                      "latitude": 34.2, "longitude": -117.2}


class Routes:
    def compute_route(self, **kwargs: Any) -> dict[str, Any]:
        assert len(kwargs["intermediates"]) == 1
        return {"routes": [{"distanceMeters": 3000, "duration": "420s", "polyline": {"encodedPolyline": "encoded"},
                            "legs": [{"distanceMeters": 1000, "duration": "120s", "steps": [
                                {"distanceMeters": 100, "staticDuration": "20s", "navigationInstruction": {"instructions": "Turn left", "maneuver": "TURN_LEFT"}}]},
                                     {"distanceMeters": 2000, "duration": "300s", "steps": []}]}]}


def test_navigation_returns_ordered_legs_steps_polyline_traffic_eta_and_maps_handoff() -> None:
    service = GoogleNavigationService(Routes(), Authorization())
    route = service.day_route(CTX, date(2026, 7, 11))
    assert route["durationSeconds"] == 420 and route["trafficAware"] is True
    assert route["legs"][0]["steps"][0]["instruction"] == "Turn left"
    assert route["polyline"] == "encoded"
    assert "place-b" in route["googleMapsUrl"] and "dir_action=navigate" in route["googleMapsUrl"]
    reordered = service.reorder(CTX, date(2026, 7, 11), ["task-c", "task-b", "task-a"])
    assert [s["taskId"] for s in reordered["stops"]] == ["task-c", "task-b", "task-a"]


def test_missing_credentials_fail_honestly() -> None:
    with pytest.raises(GoogleIntegrationError) as error:
        GooglePlacesService(None).autocomplete("Cabin", "session")
    assert error.value.code == "google_places_not_configured" and error.value.retryable
