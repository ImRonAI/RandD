"""Least-privilege tool profiles for field and platform-admin agents."""

FORBIDDEN_FIELD_TOOLS = frozenset({"shell", "editor", "environment", "http_request", "load_tool"})

FIELD_TOOL_ALLOWLIST = frozenset({
    "list_room_types", "create_room", "update_room", "archive_room", "list_rooms",
    "create_asset", "update_asset", "move_asset", "attach_original_photo",
    "find_duplicate_assets", "identify_asset_from_view", "lookup_product_information",
    "record_research_result", "mark_low_confidence_value", "get_inspection_state",
    "save_walkthrough_progress", "complete_onboarding_assessment", "take_photo",
    "take_video", "record_check", "record_section_note", "request_approval",
})


def validate_field_tools(tool_names) -> None:
    requested = set(tool_names)
    disallowed = requested - FIELD_TOOL_ALLOWLIST
    if disallowed:
        raise ValueError(f"field profile contains non-allowlisted tools: {', '.join(sorted(disallowed))}")
