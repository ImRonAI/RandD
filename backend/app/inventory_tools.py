"""Session-bound Strands tools over the existing Vantage repositories."""

from __future__ import annotations

from typing import Any

from strands import tool

from app.vantage.context import TenantContext
from app.vantage.domain import DomainError


WRITE_ROLES = ("ORG_ADMIN", "PROPERTY_MANAGER", "INSPECTOR")


def _error(error: DomainError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
            "fields": error.fields,
        },
    }


def build_inventory_tools(repository: Any, context: TenantContext) -> list[Any]:
    """Build tools whose tenant identity comes only from the verified session."""

    def call(method: str, *args: Any, read_only: bool = False, **kwargs: Any) -> Any:
        if not read_only and not context.has_role(*WRITE_ROLES):
            return _error(DomainError("forbidden", "This role has read-only access"))
        transaction = getattr(
            repository,
            "read_only_transaction" if read_only else "transaction",
            None,
        )
        try:
            if transaction is None:
                return getattr(repository, method)(*args, **kwargs)
            with transaction(context) as active:
                return getattr(active, method)(*args, **kwargs)
        except DomainError as error:
            return _error(error)

    @tool
    def list_portfolios() -> Any:
        """List portfolios in the inspector's active organization."""
        return call("list_portfolios", context.organization_id, read_only=True)

    @tool
    def create_portfolio(name: str, client_id: str) -> Any:
        """Create a replay-safe portfolio in the active organization."""
        return call(
            "create_portfolio",
            context.organization_id,
            context.user_id,
            name,
            client_id,
        )

    @tool
    def create_home(
        portfolio_id: str,
        name: str,
        client_id: str,
        unit_code: str = "",
        formatted_address: str = "",
    ) -> Any:
        """Create a home inside an existing portfolio."""
        return call(
            "create_home",
            context.organization_id,
            context.user_id,
            portfolio_id,
            name,
            client_id,
            unit_code=unit_code or None,
            formatted_address=formatted_address or None,
        )

    @tool
    def start_onboarding_inspection(home_id: str, client_id: str) -> Any:
        """Start a replay-safe onboarding inspection for a home."""
        return call(
            "start_inspection",
            context.organization_id,
            context.user_id,
            home_id,
            "onboarding",
            client_id,
        )

    @tool
    def list_room_types() -> Any:
        """List the fixed room and outdoor-area catalog."""
        return call("list_room_types", context.organization_id, read_only=True)

    @tool
    def list_rooms(home_id: str) -> Any:
        """List active rooms belonging to a home."""
        return call("list_rooms", context.organization_id, home_id, read_only=True)

    @tool
    def create_room(
        home_id: str,
        room_type_id: str,
        name: str,
        client_id: str,
        inspection_id: str = "",
    ) -> Any:
        """Create a room or outdoor area in a home."""
        return call(
            "create_room",
            context.organization_id,
            context.user_id,
            home_id,
            inspection_id or None,
            room_type_id,
            name,
            client_id,
        )

    @tool
    def update_room(
        room_id: str,
        name: str = "",
        room_type_id: str = "",
        floor_area: str = "",
        notes: str = "",
        display_order: int | None = None,
    ) -> Any:
        """Update supplied room fields."""
        values = {
            "name": name or None,
            "room_type_id": room_type_id or None,
            "floor_area": floor_area or None,
            "notes": notes or None,
            "display_order": display_order,
        }
        return call(
            "update_room",
            context.organization_id,
            context.user_id,
            room_id,
            **{key: value for key, value in values.items() if value is not None},
        )

    @tool
    def create_asset(
        room_id: str,
        client_id: str,
        asset_type: str = "",
        name: str = "",
        inspection_id: str = "",
        location_description: str = "",
        manufacturer: str = "",
        model_number: str = "",
        serial_number: str = "",
        quantity: int | None = None,
        condition: str = "",
        condition_notes: str = "",
        purchase_date: str = "",
        purchase_price: str = "",
        estimated_current_value: str = "",
        estimated_replacement_cost: str = "",
        warranty_provider: str = "",
        warranty_expiration: str = "",
        dimensions: str = "",
        color_finish: str = "",
        installation_date: str = "",
        last_service_date: str = "",
        product_identifier: str = "",
        notes: str = "",
        tags: list[str] | None = None,
    ) -> Any:
        """Create an asset in a room with any known metadata fields."""
        metadata = {
            "location_description": location_description or None,
            "manufacturer": manufacturer or None,
            "model_number": model_number or None,
            "serial_number": serial_number or None,
            "quantity": quantity,
            "condition": condition or None,
            "condition_notes": condition_notes or None,
            "purchase_date": purchase_date or None,
            "purchase_price": purchase_price or None,
            "estimated_current_value": estimated_current_value or None,
            "estimated_replacement_cost": estimated_replacement_cost or None,
            "warranty_provider": warranty_provider or None,
            "warranty_expiration": warranty_expiration or None,
            "dimensions": dimensions or None,
            "color_finish": color_finish or None,
            "installation_date": installation_date or None,
            "last_service_date": last_service_date or None,
            "product_identifier": product_identifier or None,
            "notes": notes or None,
            "tags": tags,
        }
        return call(
            "create_asset",
            context.organization_id,
            context.user_id,
            room_id,
            inspection_id or None,
            asset_type,
            name,
            client_id,
            **{key: value for key, value in metadata.items() if value is not None},
        )

    @tool
    def update_asset(asset_id: str, changes: dict[str, Any]) -> Any:
        """Update any supported asset metadata fields."""
        return call(
            "update_asset",
            context.organization_id,
            context.user_id,
            asset_id,
            **changes,
        )

    @tool
    def move_asset(asset_id: str, target_room_id: str) -> Any:
        """Move an asset to another room in the same home."""
        return call(
            "move_asset",
            context.organization_id,
            context.user_id,
            asset_id,
            target_room_id,
        )

    @tool
    def record_asset_document(
        asset_id: str,
        kind: str,
        photo_id: str = "",
        source_url: str = "",
    ) -> Any:
        """Link a verified receipt/warranty photo or an online document to an asset."""
        return call(
            "record_asset_document",
            context.organization_id,
            asset_id,
            kind,
            photo_id=photo_id or None,
            source_url=source_url or None,
        )

    @tool
    def list_asset_documents(asset_id: str) -> Any:
        """List documents attached to an asset."""
        return call(
            "list_asset_documents",
            context.organization_id,
            asset_id,
            read_only=True,
        )

    @tool
    def record_asset_research_value(
        asset_id: str,
        field_name: str,
        value: Any,
        provenance: str,
        source_reference: str = "",
        confidence: float | None = None,
        confirmed: bool = False,
    ) -> Any:
        """Record one observed, extracted, user-entered, or researched asset fact."""
        return call(
            "record_asset_research_value",
            context.organization_id,
            asset_id,
            field_name=field_name,
            value=value,
            provenance=provenance,
            source_reference=source_reference or None,
            confidence=confidence,
            confirmed=confirmed,
        )

    @tool
    def list_asset_research_values(asset_id: str) -> Any:
        """List provenance-bearing facts recorded for an asset."""
        return call(
            "list_asset_research_values",
            context.organization_id,
            asset_id,
            read_only=True,
        )

    return [
        list_portfolios,
        create_portfolio,
        create_home,
        start_onboarding_inspection,
        list_room_types,
        list_rooms,
        create_room,
        update_room,
        create_asset,
        update_asset,
        move_asset,
        record_asset_document,
        list_asset_documents,
        record_asset_research_value,
        list_asset_research_values,
    ]
