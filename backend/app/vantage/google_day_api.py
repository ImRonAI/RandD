from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .context import TenantContext
from .google_day import GoogleCalendarService, GoogleIntegrationError, GoogleNavigationService, GooglePlacesService


class PlaceResolve(BaseModel):
    placeId: str
    sessionToken: str
    homeId: str | None = None


class RouteReorder(BaseModel):
    orderedTaskIds: list[str] = Field(min_length=1)
    date: date


def _raise(error: GoogleIntegrationError) -> None:
    status_code = 503 if error.code.endswith("not_configured") else (403 if error.code.endswith("forbidden") else 422)
    raise HTTPException(status_code=status_code, detail={"error": {"code": error.code, "message": str(error),
                                                                    "retryable": error.retryable, "fields": {}}}) from error


def create_google_day_router(*, calendar: GoogleCalendarService, places: GooglePlacesService,
                             navigation: GoogleNavigationService,
                             context_dependency: Callable[..., TenantContext]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["google-day"])
    Context = Annotated[TenantContext, Depends(context_dependency)]

    @router.get("/calendar/connections")
    def connections(context: Context) -> list[dict[str, Any]]:
        return calendar.connections(context)

    @router.post("/calendar/sync")
    def sync(context: Context) -> dict[str, Any]:
        try: return calendar.sync(context)
        except GoogleIntegrationError as error: _raise(error)

    @router.get("/calendar/day")
    def calendar_day(context: Context, date_: date = Query(alias="date")) -> dict[str, Any]:
        return calendar.day(context, date_)

    @router.get("/places/autocomplete")
    def autocomplete(context: Context, input_: str = Query(alias="input"), session_token: str = Query(alias="sessionToken")) -> list[dict[str, Any]]:
        del context
        try: return places.autocomplete(input_, session_token)
        except GoogleIntegrationError as error: _raise(error)

    @router.post("/places/resolve")
    def resolve(payload: PlaceResolve, context: Context) -> dict[str, Any]:
        try:
            place = places.resolve(payload.placeId, payload.sessionToken)
            if payload.homeId:
                return navigation.authorization.save_home_place(context, payload.homeId, place)
            return place
        except GoogleIntegrationError as error: _raise(error)

    @router.get("/navigation/day-route")
    def day_route(context: Context, date_: date = Query(alias="date")) -> dict[str, Any]:
        try: return navigation.day_route(context, date_)
        except GoogleIntegrationError as error: _raise(error)

    @router.post("/navigation/day-route/reorder")
    def reorder(payload: RouteReorder, context: Context) -> dict[str, Any]:
        try: return navigation.reorder(context, payload.date, payload.orderedTaskIds)
        except GoogleIntegrationError as error: _raise(error)

    return router
