from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from .context import TenantContext
from .domain import ConflictError, DomainError, VantageRepository


class InspectionCreate(BaseModel):
    homeId: str
    type: str
    clientId: str


class RoomCreate(BaseModel):
    roomTypeId: str
    name: str
    inspectionId: str | None = None
    clientId: str


class AssetCreate(BaseModel):
    assetType: str = ""
    name: str = ""
    inspectionId: str | None = None
    clientId: str


class RoomUpdate(BaseModel):
    roomTypeId: str | None = None
    name: str | None = None
    floorArea: str | None = None
    notes: str | None = None
    displayOrder: int | None = None


class AssetUpdate(BaseModel):
    assetType: str | None = None
    name: str | None = None
    locationDescription: str | None = None
    manufacturer: str | None = None
    modelNumber: str | None = None
    serialNumber: str | None = None
    condition: str | None = None
    conditionNotes: str | None = None
    notes: str | None = None
    roomId: str | None = None


class UploadCreate(BaseModel):
    homeId: str
    roomId: str
    assetId: str
    inspectionId: str | None = None
    clientId: str


class UploadComplete(BaseModel):
    objectKey: str
    sha256: str = Field(min_length=64, max_length=64)
    byteSize: int = Field(gt=0)
    mimeType: str


def _raise(error: DomainError) -> None:
    status_code = status.HTTP_409_CONFLICT if isinstance(error, ConflictError) else (
        status.HTTP_404_NOT_FOUND if error.code == "not_found" else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    raise HTTPException(status_code=status_code, detail={"error": {
        "code": error.code, "message": str(error), "retryable": error.retryable, "fields": error.fields,
    }}) from error


def _require_write(context: TenantContext) -> None:
    if not context.has_role("ORG_ADMIN", "PROPERTY_MANAGER", "INSPECTOR"):
        raise HTTPException(status_code=403, detail={"error": {"code": "forbidden", "message": "This role has read-only access", "retryable": False, "fields": {}}})


def _require_home_read(context: TenantContext, home_id: str) -> None:
    if context.has_role("OWNER") and home_id not in context.home_grants:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Home was not found", "retryable": False, "fields": {}}})


def create_vantage_router(
    repository: VantageRepository,
    context_dependency: Callable[..., TenantContext],
) -> APIRouter:
    """Build routes without global auth/database state.

    `context_dependency` must verify the secure session and active membership;
    request payloads never contain or override organization/user identity.
    """
    router = APIRouter(prefix="/api", tags=["vantage-v1"])
    Context = Annotated[TenantContext, Depends(context_dependency)]

    @router.get("/room-types")
    def room_types(context: Context) -> list[dict[str, Any]]:
        return repository.list_room_types(context.organization_id)

    @router.post("/inspections", status_code=201)
    def start_inspection(payload: InspectionCreate, context: Context) -> dict[str, Any]:
        _require_write(context)
        _require_home_read(context, payload.homeId)
        try:
            return repository.start_inspection(context.organization_id, context.user_id, payload.homeId, payload.type, payload.clientId)
        except DomainError as error:
            _raise(error)

    @router.get("/inspections/{inspection_id}")
    def get_inspection(inspection_id: str, context: Context) -> dict[str, Any]:
        try:
            inspection = repository.get_inspection(context.organization_id, inspection_id)
            _require_home_read(context, inspection["home_id"])
            return inspection
        except DomainError as error:
            _raise(error)

    @router.post("/inspections/{inspection_id}/complete")
    def complete_inspection(inspection_id: str, context: Context) -> dict[str, Any]:
        _require_write(context)
        try:
            return repository.complete_onboarding(context.organization_id, context.user_id, inspection_id)
        except DomainError as error:
            _raise(error)

    @router.get("/homes/{home_id}/rooms")
    def rooms(home_id: str, context: Context) -> list[dict[str, Any]]:
        _require_home_read(context, home_id)
        try:
            return repository.list_rooms(context.organization_id, home_id)
        except DomainError as error:
            _raise(error)

    @router.post("/homes/{home_id}/rooms", status_code=201)
    def create_room(home_id: str, payload: RoomCreate, context: Context, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        _require_write(context)
        _require_home_read(context, home_id)
        try:
            return repository.create_room(context.organization_id, context.user_id, home_id, payload.inspectionId, payload.roomTypeId, payload.name, payload.clientId or idempotency_key or "")
        except DomainError as error:
            _raise(error)

    @router.patch("/rooms/{room_id}")
    def update_room(room_id: str, payload: RoomUpdate, context: Context) -> dict[str, Any]:
        _require_write(context)
        values = {
            "room_type_id": payload.roomTypeId,
            "name": payload.name,
            "floor_area": payload.floorArea,
            "notes": payload.notes,
            "display_order": payload.displayOrder,
        }
        try:
            return repository.update_room(
                context.organization_id,
                context.user_id,
                room_id,
                **{key: value for key, value in values.items() if value is not None},
            )
        except DomainError as error:
            _raise(error)

    @router.delete("/rooms/{room_id}")
    def archive_room(room_id: str, context: Context) -> dict[str, Any]:
        _require_write(context)
        try:
            return repository.archive_room(context.organization_id, context.user_id, room_id)
        except DomainError as error:
            _raise(error)

    @router.get("/rooms/{room_id}/assets")
    def assets(room_id: str, context: Context) -> list[dict[str, Any]]:
        try:
            room = repository.get_room(context.organization_id, room_id)
            _require_home_read(context, room["home_id"])
            return repository.list_assets(context.organization_id, room_id)
        except DomainError as error:
            _raise(error)

    @router.post("/rooms/{room_id}/assets", status_code=201)
    def create_asset(room_id: str, payload: AssetCreate, context: Context, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        _require_write(context)
        try:
            return repository.create_asset(context.organization_id, context.user_id, room_id, payload.inspectionId, payload.assetType, payload.name, payload.clientId or idempotency_key or "")
        except DomainError as error:
            _raise(error)

    @router.patch("/assets/{asset_id}")
    def update_asset(asset_id: str, payload: AssetUpdate, context: Context) -> dict[str, Any]:
        _require_write(context)
        values = {
            "asset_type": payload.assetType, "name": payload.name, "location_description": payload.locationDescription,
            "manufacturer": payload.manufacturer, "model_number": payload.modelNumber, "serial_number": payload.serialNumber,
            "condition": payload.condition, "condition_notes": payload.conditionNotes, "notes": payload.notes,
        }
        try:
            if payload.roomId is not None:
                repository.move_asset(context.organization_id, context.user_id, asset_id, payload.roomId)
            return repository.update_asset(context.organization_id, context.user_id, asset_id, **{k: v for k, v in values.items() if v is not None})
        except DomainError as error:
            _raise(error)

    @router.post("/media/uploads", status_code=201)
    def create_upload(payload: UploadCreate, context: Context) -> dict[str, Any]:
        _require_write(context)
        _require_home_read(context, payload.homeId)
        try:
            return repository.create_photo_upload(context.organization_id, context.user_id, payload.homeId, payload.roomId, payload.assetId, payload.inspectionId, payload.clientId)
        except DomainError as error:
            _raise(error)

    @router.post("/media/uploads/{upload_id}/complete")
    def complete_upload(upload_id: str, payload: UploadComplete, context: Context) -> dict[str, Any]:
        _require_write(context)
        del upload_id, payload, context
        raise HTTPException(status_code=409, detail={"error": {
            "code": "server_verification_required",
            "message": "Original completion requires the server-owned storage verification path",
            "retryable": False,
            "fields": {},
        }})

    return router
