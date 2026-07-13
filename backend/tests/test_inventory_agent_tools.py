from __future__ import annotations

from contextlib import contextmanager

from app.inventory_tools import build_inventory_tools
from app.prompts import SYSTEM_PROMPT
from app.vantage.context import TenantContext


class RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"operation": name, "args": args, "kwargs": kwargs}

        return record


class RecordingAdapter:
    def __init__(self) -> None:
        self.repository = RecordingRepository()
        self.transactions: list[tuple[str, TenantContext]] = []

    @contextmanager
    def transaction(self, context: TenantContext):
        self.transactions.append(("write", context))
        yield self.repository

    @contextmanager
    def read_only_transaction(self, context: TenantContext):
        self.transactions.append(("read", context))
        yield self.repository


CONTEXT = TenantContext(
    user_id="user-1",
    organization_id="org-1",
    roles=frozenset({"INSPECTOR"}),
    home_grants=frozenset(),
)


def _tools(adapter: RecordingAdapter) -> dict[str, object]:
    return {tool.tool_name: tool for tool in build_inventory_tools(adapter, CONTEXT)}


def test_inventory_tool_factory_exposes_onboarding_operations() -> None:
    names = set(_tools(RecordingAdapter()))
    assert {
        "list_portfolios",
        "create_portfolio",
        "create_home",
        "start_onboarding_inspection",
        "list_room_types",
        "list_rooms",
        "create_room",
        "update_room",
        "create_asset",
        "update_asset",
        "move_asset",
        "record_asset_document",
        "list_asset_documents",
        "record_asset_research_value",
        "list_asset_research_values",
    } <= names


def test_system_prompt_adds_direct_asset_metadata_guidance_without_losing_existing_instructions() -> None:
    assert "## QC TURNOVER INSPECTIONS (camera + checklist)" in SYSTEM_PROMPT
    assert "## LONG-TERM MEMORY" in SYSTEM_PROMPT
    assert "pass known canonical asset fields directly to create_asset" in SYSTEM_PROMPT
    assert "record_asset_research_value preserves provenance" in SYSTEM_PROMPT


def test_inventory_tools_bind_identity_and_transaction_mode() -> None:
    adapter = RecordingAdapter()
    tools = _tools(adapter)

    portfolio = tools["create_portfolio"](name="Lakefront", client_id="client-1")
    portfolios = tools["list_portfolios"]()

    assert portfolio["operation"] == "create_portfolio"
    assert adapter.repository.calls[0] == (
        "create_portfolio",
        ("org-1", "user-1", "Lakefront", "client-1"),
        {},
    )
    assert portfolios["operation"] == "list_portfolios"
    assert adapter.repository.calls[1] == ("list_portfolios", ("org-1",), {})
    assert [mode for mode, _ in adapter.transactions] == ["write", "read"]


def test_create_home_and_inspection_use_server_tenant_context() -> None:
    adapter = RecordingAdapter()
    tools = _tools(adapter)

    tools["create_home"](
        portfolio_id="portfolio-1",
        name="Cabin 7",
        client_id="home-client",
        unit_code="C7",
        formatted_address="7 Lake Road",
    )
    tools["start_onboarding_inspection"](home_id="home-1", client_id="inspection-client")

    assert adapter.repository.calls[0] == (
        "create_home",
        ("org-1", "user-1", "portfolio-1", "Cabin 7", "home-client"),
        {"unit_code": "C7", "formatted_address": "7 Lake Road"},
    )
    assert adapter.repository.calls[1] == (
        "start_inspection",
        ("org-1", "user-1", "home-1", "onboarding", "inspection-client"),
        {},
    )


def test_create_asset_exposes_and_forwards_full_metadata_fields() -> None:
    adapter = RecordingAdapter()
    create_asset = _tools(adapter)["create_asset"]
    properties = create_asset.tool_spec["inputSchema"]["json"]["properties"]

    for field in (
        "manufacturer",
        "model_number",
        "serial_number",
        "quantity",
        "purchase_date",
        "purchase_price",
        "estimated_replacement_cost",
        "warranty_provider",
        "warranty_expiration",
        "tags",
    ):
        assert field in properties
    assert "metadata" not in properties

    create_asset(
        room_id="room-1",
        client_id="asset-client",
        asset_type="irrigation",
        name="Irrigation Controller",
        inspection_id="inspection-1",
        manufacturer="Rain Bird",
        model_number="ESP-TM2",
        serial_number="RB-001",
        quantity=1,
        purchase_date="2025-03-15",
        purchase_price="189.99",
        estimated_replacement_cost="2499.00",
        warranty_provider="Rain Bird",
        warranty_expiration="2028-03-15",
        tags=["outdoor", "irrigation"],
    )

    assert adapter.repository.calls[-1] == (
        "create_asset",
        (
            "org-1",
            "user-1",
            "room-1",
            "inspection-1",
            "irrigation",
            "Irrigation Controller",
            "asset-client",
        ),
        {
            "manufacturer": "Rain Bird",
            "model_number": "ESP-TM2",
            "serial_number": "RB-001",
            "quantity": 1,
            "purchase_date": "2025-03-15",
            "purchase_price": "189.99",
            "estimated_replacement_cost": "2499.00",
            "warranty_provider": "Rain Bird",
            "warranty_expiration": "2028-03-15",
            "tags": ["outdoor", "irrigation"],
        },
    )


def test_document_tool_accepts_photo_or_source_url_without_object_key() -> None:
    adapter = RecordingAdapter()
    tools = _tools(adapter)

    tools["record_asset_document"](
        asset_id="asset-1",
        kind="receipt",
        photo_id="photo-1",
        source_url="",
    )

    name, args, kwargs = adapter.repository.calls[0]
    assert name == "record_asset_document"
    assert args == ("org-1", "asset-1", "receipt")
    assert kwargs == {"photo_id": "photo-1", "source_url": None}
    assert "object_key" not in kwargs


def test_read_only_role_cannot_use_mutating_inventory_tools() -> None:
    adapter = RecordingAdapter()
    owner = TenantContext("owner-1", "org-1", frozenset({"OWNER"}), frozenset())
    tools = {tool.tool_name: tool for tool in build_inventory_tools(adapter, owner)}

    result = tools["create_portfolio"](name="Blocked", client_id="client-1")

    assert result["ok"] is False
    assert result["error"]["code"] == "forbidden"
    assert adapter.repository.calls == []
