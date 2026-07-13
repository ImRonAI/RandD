"""Provider-neutral agent operations over an authorization-aware repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolContext:
    org_id: str
    user_id: str
    roles: frozenset[str]
    home_id: str
    inspection_id: str
    session_id: str


class InventoryRepository(Protocol):
    async def list_room_types(self, context: ToolContext) -> Any: ...
    async def list_rooms(self, context: ToolContext) -> Any: ...
    async def create_room(self, context: ToolContext, payload: dict, idempotency_key: str) -> Any: ...


class TransientRepositoryError(RuntimeError):
    """Repository/network failure that is safe for the caller to retry."""


class AgentInventoryService:
    """Thin tool boundary; repositories remain responsible for entity ownership checks."""

    def __init__(self, repository: InventoryRepository) -> None:
        self.repository = repository

    @staticmethod
    def _error(code: str, message: str, *, retryable: bool = False,
               fields: dict[str, str] | None = None) -> dict:
        return {"ok": False, "error": {"code": code, "message": message,
                                         "retryable": retryable, "fields": fields or {}}}

    @staticmethod
    def _valid(context: ToolContext) -> bool:
        return all((context.org_id, context.user_id, context.home_id,
                    context.inspection_id, context.session_id))

    async def _call(self, context: ToolContext, method: str, *args: Any) -> dict:
        if not self._valid(context):
            return self._error("authorization_context_missing", "Authenticated tool context is required")
        try:
            result = await getattr(self.repository, method)(context, *args)
            return {"ok": True, "data": result}
        except PermissionError as exc:
            return self._error("forbidden", str(exc))
        except (ValueError, KeyError) as exc:
            return self._error("invalid_reference", str(exc))
        except (TransientRepositoryError, TimeoutError, ConnectionError) as exc:
            return self._error("temporarily_unavailable", str(exc), retryable=True)

    async def list_room_types(self, context: ToolContext) -> dict:
        return await self._call(context, "list_room_types")

    async def list_rooms(self, context: ToolContext) -> dict:
        return await self._call(context, "list_rooms")

    async def create_room(self, context: ToolContext, payload: dict,
                          idempotency_key: str) -> dict:
        if not idempotency_key or not payload.get("client_id"):
            return self._error("idempotency_required", "client_id and idempotency key are required")
        return await self._call(context, "create_room", payload, idempotency_key)

    async def invoke(self, operation: str, context: ToolContext, **kwargs: Any) -> dict:
        """Extensible structured bridge for the remaining repository operations."""
        allowed = {
            "update_room", "archive_room", "create_asset", "update_asset", "move_asset",
            "attach_original_photo", "find_duplicate_assets", "record_research_result",
            "mark_low_confidence_value", "get_inspection_state", "save_walkthrough_progress",
            "complete_onboarding_assessment",
        }
        if operation not in allowed:
            return self._error("unknown_operation", f"Unsupported operation: {operation}")
        mutating = allowed - {"find_duplicate_assets", "get_inspection_state"}
        if operation in mutating:
            client_id = kwargs.pop("client_id", None)
            idempotency_key = kwargs.pop("idempotency_key", None)
            if not client_id or not idempotency_key:
                return self._error(
                    "idempotency_required",
                    "client_id and idempotency_key are required for mutating operations",
                    fields={"client_id": "required", "idempotency_key": "required"},
                )
            kwargs["client_id"] = client_id
            return await self._call(context, operation, kwargs, idempotency_key)
        return await self._call(context, operation, kwargs)
