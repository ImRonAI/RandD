from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .google_day import ExpiredSyncToken, GoogleIntegrationError


def _json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Google endpoints
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 410:
            raise ExpiredSyncToken() from error
        retryable = error.code == 429 or error.code >= 500
        raise GoogleIntegrationError("google_api_error", f"Google API returned HTTP {error.code}", retryable=retryable) from error
    except (URLError, TimeoutError) as error:
        raise GoogleIntegrationError("google_api_unavailable", "Google API is unavailable", retryable=True) from error


class GoogleCalendarHttpClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise GoogleIntegrationError("google_calendar_not_configured", "Google Calendar access token is missing", retryable=True)
        self.access_token = access_token

    def list_events(self, *, calendar_id: str, page_token: str | None = None,
                    sync_token: str | None = None) -> dict[str, Any]:
        params: dict[str, str] = {"maxResults": "2500", "showDeleted": "true", "singleEvents": "true"}
        if page_token:
            params["pageToken"] = page_token
        if sync_token:
            params["syncToken"] = sync_token
        url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events?{urlencode(params)}"
        return _json(Request(url, headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}))


class GooglePlacesHttpClient:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise GoogleIntegrationError("google_places_not_configured", "Google Places API key is missing", retryable=True)
        self.api_key = api_key

    def autocomplete(self, *, text: str, session_token: str) -> list[dict[str, Any]]:
        request = Request("https://places.googleapis.com/v1/places:autocomplete", method="POST",
                          data=json.dumps({"input": text, "sessionToken": session_token}).encode(),
                          headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text",
                                   "Content-Type": "application/json"})
        raw = _json(request)
        return [{"placeId": item["placePrediction"].get("placeId"),
                 "text": (item["placePrediction"].get("text") or {}).get("text")}
                for item in raw.get("suggestions", []) if item.get("placePrediction")]

    def details(self, *, place_id: str, session_token: str, fields: tuple[str, ...]) -> dict[str, Any]:
        url = f"https://places.googleapis.com/v1/places/{quote(place_id, safe='')}?{urlencode({'sessionToken': session_token})}"
        return _json(Request(url, headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": ",".join(fields), "Accept": "application/json"}))


class GoogleRoutesHttpClient:
    FIELD_MASK = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,routes.legs.distanceMeters,routes.legs.duration,routes.legs.steps.distanceMeters,routes.legs.steps.staticDuration,routes.legs.steps.navigationInstruction"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise GoogleIntegrationError("google_routes_not_configured", "Google Routes API key is missing", retryable=True)
        self.api_key = api_key

    def compute_route(self, *, origin: dict[str, float], destination: dict[str, float],
                      intermediates: list[dict[str, float]], departure_time: datetime) -> dict[str, Any]:
        waypoint = lambda point: {"location": {"latLng": point}}
        payload = {"origin": waypoint(origin), "destination": waypoint(destination),
                   "intermediates": [waypoint(point) for point in intermediates], "travelMode": "DRIVE",
                   "routingPreference": "TRAFFIC_AWARE", "departureTime": departure_time.isoformat().replace("+00:00", "Z"),
                   "computeAlternativeRoutes": False, "polylineQuality": "HIGH_QUALITY"}
        return _json(Request("https://routes.googleapis.com/directions/v2:computeRoutes", method="POST",
                             data=json.dumps(payload).encode(), headers={"X-Goog-Api-Key": self.api_key,
                             "X-Goog-FieldMask": self.FIELD_MASK, "Content-Type": "application/json"}))
