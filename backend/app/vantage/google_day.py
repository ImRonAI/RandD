from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from .context import TenantContext


class GoogleIntegrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ExpiredSyncToken(GoogleIntegrationError):
    def __init__(self) -> None:
        super().__init__("calendar_sync_token_expired", "Google Calendar sync token expired", retryable=True)


class CalendarClient(Protocol):
    def list_events(self, *, calendar_id: str, page_token: str | None = None,
                    sync_token: str | None = None) -> dict[str, Any]: ...


class PlacesClient(Protocol):
    def autocomplete(self, *, text: str, session_token: str) -> list[dict[str, Any]]: ...
    def details(self, *, place_id: str, session_token: str,
                fields: tuple[str, ...]) -> dict[str, Any]: ...


class RoutesClient(Protocol):
    def compute_route(self, *, origin: dict[str, float], destination: dict[str, float],
                      intermediates: list[dict[str, float]], departure_time: datetime) -> dict[str, Any]: ...


class DayAuthorization(Protocol):
    """All entity lookup is scoped by the verified context, never payload org IDs."""

    def calendar_connection(self, context: TenantContext) -> dict[str, Any] | None: ...
    def authorize_calendar_link(self, context: TenantContext, properties: dict[str, str]) -> dict[str, Any] | None: ...
    def day_stops(self, context: TenantContext, day: date) -> list[dict[str, Any]]: ...
    def authorize_task_ids(self, context: TenantContext, day: date, task_ids: list[str]) -> list[dict[str, Any]]: ...
    def save_home_place(self, context: TenantContext, home_id: str, place: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(slots=True)
class CalendarSyncState:
    sync_token: str | None = None
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    synced_at: datetime | None = None


class GoogleCalendarService:
    """Full/incremental Calendar sync with Google-compatible 410 recovery."""

    def __init__(self, client: CalendarClient | None, authorization: DayAuthorization) -> None:
        self.client = client
        self.authorization = authorization
        self._states: dict[tuple[str, str, str], CalendarSyncState] = {}

    def _client(self) -> CalendarClient:
        if self.client is None:
            raise GoogleIntegrationError("google_calendar_not_configured", "Google Calendar credentials are not configured", retryable=True)
        return self.client

    def connections(self, context: TenantContext) -> list[dict[str, Any]]:
        connection = self.authorization.calendar_connection(context)
        return [connection] if connection else []

    def sync(self, context: TenantContext) -> dict[str, Any]:
        connection = self.authorization.calendar_connection(context)
        if not connection:
            raise GoogleIntegrationError("calendar_connection_missing", "No Google Calendar is connected", retryable=False)
        calendar_id = str(connection["calendarId"])
        key = (context.organization_id, context.user_id, calendar_id)
        state = self._states.setdefault(key, CalendarSyncState())
        recovered = False
        try:
            changed, deleted, next_token = self._collect(calendar_id, state.sync_token)
        except ExpiredSyncToken:
            state.events.clear()
            state.sync_token = None
            recovered = True
            changed, deleted, next_token = self._collect(calendar_id, None)
        for event_id in deleted:
            state.events.pop(event_id, None)
        for event in changed:
            event_id = str(event["id"])
            private = (event.get("extendedProperties") or {}).get("private") or {}
            linked = self.authorization.authorize_calendar_link(context, {str(k): str(v) for k, v in private.items()})
            if linked is None:
                continue
            normalized = {**event, "vantageLink": linked}
            state.events[event_id] = normalized
        state.sync_token = next_token
        state.synced_at = datetime.now(timezone.utc)
        return {"changed": len(changed), "deleted": len(deleted), "recoveredFromExpiredToken": recovered,
                "syncTokenStored": bool(next_token), "syncedAt": state.synced_at.isoformat()}

    def _collect(self, calendar_id: str, sync_token: str | None) -> tuple[list[dict[str, Any]], list[str], str]:
        changed: list[dict[str, Any]] = []
        deleted: list[str] = []
        page_token: str | None = None
        next_sync_token: str | None = None
        while True:
            page = self._client().list_events(calendar_id=calendar_id, page_token=page_token, sync_token=sync_token)
            for event in page.get("items", []):
                if event.get("status") == "cancelled":
                    deleted.append(str(event["id"]))
                else:
                    changed.append(event)
            page_token = page.get("nextPageToken")
            if page_token:
                continue
            next_sync_token = page.get("nextSyncToken")
            break
        if not next_sync_token:
            raise GoogleIntegrationError("calendar_sync_incomplete", "Google Calendar did not return a final sync token", retryable=True)
        return changed, deleted, str(next_sync_token)

    def day(self, context: TenantContext, day: date) -> dict[str, Any]:
        connection = self.authorization.calendar_connection(context)
        if not connection:
            return {"date": day.isoformat(), "events": [], "freshness": None}
        state = self._states.get((context.organization_id, context.user_id, str(connection["calendarId"])), CalendarSyncState())
        events = [e for e in state.events.values() if _event_day(e) == day]
        return {"date": day.isoformat(), "events": sorted(events, key=_event_start),
                "freshness": state.synced_at.isoformat() if state.synced_at else None}


def _event_start(event: dict[str, Any]) -> str:
    return str((event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or "")


def _event_day(event: dict[str, Any]) -> date | None:
    value = _event_start(event)
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class GooglePlacesService:
    DETAIL_FIELDS = ("id", "displayName", "formattedAddress", "location")

    def __init__(self, client: PlacesClient | None) -> None:
        self.client = client

    def _client(self) -> PlacesClient:
        if self.client is None:
            raise GoogleIntegrationError("google_places_not_configured", "Google Places credentials are not configured", retryable=True)
        return self.client

    def autocomplete(self, text: str, session_token: str) -> list[dict[str, Any]]:
        if not text.strip() or not session_token.strip():
            raise GoogleIntegrationError("invalid_places_request", "Input and sessionToken are required")
        return self._client().autocomplete(text=text.strip(), session_token=session_token)

    def resolve(self, place_id: str, session_token: str) -> dict[str, Any]:
        if not place_id or not session_token:
            raise GoogleIntegrationError("invalid_places_request", "placeId and sessionToken are required")
        raw = self._client().details(place_id=place_id, session_token=session_token, fields=self.DETAIL_FIELDS)
        location = raw.get("location") or {}
        return {"placeId": raw.get("id"), "displayName": (raw.get("displayName") or {}).get("text"),
                "formattedAddress": raw.get("formattedAddress"), "latitude": location.get("latitude"),
                "longitude": location.get("longitude")}


class GoogleNavigationService:
    def __init__(self, client: RoutesClient | None, authorization: DayAuthorization) -> None:
        self.client = client
        self.authorization = authorization
        self._orders: dict[tuple[str, str, date], list[str]] = {}

    def _client(self) -> RoutesClient:
        if self.client is None:
            raise GoogleIntegrationError("google_routes_not_configured", "Google Routes credentials are not configured", retryable=True)
        return self.client

    def reorder(self, context: TenantContext, day: date, task_ids: list[str]) -> dict[str, Any]:
        authorized = self.authorization.authorize_task_ids(context, day, task_ids)
        if len(authorized) != len(task_ids) or {s["taskId"] for s in authorized} != set(task_ids):
            raise GoogleIntegrationError("route_stop_forbidden", "One or more route stops are not authorized")
        self._orders[(context.organization_id, context.user_id, day)] = task_ids[:]
        return self.day_route(context, day)

    def day_route(self, context: TenantContext, day: date) -> dict[str, Any]:
        stops = self.authorization.day_stops(context, day)
        order = self._orders.get((context.organization_id, context.user_id, day))
        if order:
            by_id = {s["taskId"]: s for s in stops}
            stops = [by_id[i] for i in order if i in by_id]
        if len(stops) < 2:
            return {"date": day.isoformat(), "stops": stops, "legs": [], "distanceMeters": 0,
                    "durationSeconds": 0, "polyline": None, "googleMapsUrl": _maps_url(stops),
                    "routeGeneratedAt": datetime.now(timezone.utc).isoformat(), "connectionStatus": "connected"}
        points = [{"latitude": float(s["latitude"]), "longitude": float(s["longitude"])} for s in stops]
        raw = self._client().compute_route(origin=points[0], destination=points[-1], intermediates=points[1:-1],
                                           departure_time=datetime.now(timezone.utc))
        route = (raw.get("routes") or [{}])[0]
        legs = []
        cumulative_seconds = 0
        route_url = _maps_url(stops)
        for index, leg in enumerate(route.get("legs") or []):
            duration_seconds = _seconds(leg.get("duration"))
            cumulative_seconds += duration_seconds
            distance_meters = int(leg.get("distanceMeters", 0))
            from_label = _stop_label(stops[index])
            to_label = _stop_label(stops[index + 1])
            legs.append({"id": f"{day.isoformat()}:{index}", "fromTaskId": stops[index]["taskId"],
                         "toTaskId": stops[index + 1]["taskId"], "fromLabel": from_label, "toLabel": to_label,
                         "distanceMeters": distance_meters, "distanceText": _distance_text(distance_meters),
                         "durationSeconds": duration_seconds, "durationText": _duration_text(duration_seconds),
                         "eta": datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + cumulative_seconds, timezone.utc).isoformat(),
                         "googleMapsUrl": route_url, "trafficAware": True, "steps": [
                             {"id": f"{day.isoformat()}:{index}:{step_index}",
                              "instruction": (step.get("navigationInstruction") or {}).get("instructions", ""),
                              "maneuver": (step.get("navigationInstruction") or {}).get("maneuver"),
                              "distanceMeters": step.get("distanceMeters", 0),
                              "distanceText": _distance_text(int(step.get("distanceMeters", 0))),
                              "durationSeconds": _seconds(step.get("staticDuration")),
                              "durationText": _duration_text(_seconds(step.get("staticDuration")))}
                             for step_index, step in enumerate(leg.get("steps") or [])]})
        return {"date": day.isoformat(), "stops": stops, "legs": legs,
                "distanceMeters": route.get("distanceMeters", sum(x["distanceMeters"] for x in legs)),
                "durationSeconds": _seconds(route.get("duration")) or sum(x["durationSeconds"] for x in legs),
                "polyline": (route.get("polyline") or {}).get("encodedPolyline"), "googleMapsUrl": route_url,
                "trafficAware": True, "routeGeneratedAt": datetime.now(timezone.utc).isoformat(),
                "connectionStatus": "connected"}


def _stop_label(stop: dict[str, Any]) -> str:
    home = stop.get("home") or {}
    return str(home.get("name") or stop.get("homeName") or stop.get("name") or stop.get("homeId") or "Stop")


def _distance_text(meters: int) -> str:
    miles = max(0, meters) / 1609.344
    return f"{miles:.1f} mi" if miles < 10 else f"{miles:.0f} mi"


def _duration_text(seconds: int) -> str:
    minutes = max(0, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} hr {remainder} min" if remainder else f"{hours} hr"


def _seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.endswith("s"):
        try:
            return int(float(value[:-1]))
        except ValueError:
            return 0
    return 0


def _maps_url(stops: list[dict[str, Any]]) -> str | None:
    if len(stops) < 2:
        return None
    destination = stops[-1].get("placeId") or f'{stops[-1]["latitude"]},{stops[-1]["longitude"]}'
    params: dict[str, str] = {"api": "1", "origin": f'{stops[0]["latitude"]},{stops[0]["longitude"]}',
                              "destination": str(destination), "travelmode": "driving", "dir_action": "navigate"}
    if len(stops) > 2:
        params["waypoints"] = "|".join(str(s.get("placeId") or f'{s["latitude"]},{s["longitude"]}') for s in stops[1:-1])
    return "https://www.google.com/maps/dir/?" + urlencode(params, quote_via=quote)
