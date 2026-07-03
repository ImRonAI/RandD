"""Guardrails — confirmation before consequential actions (TASKS.md M2.5).

Two layers, kept deliberately simple:

1. :func:`requires_confirmation` — the pure policy: which tool calls are
   consequential enough to need an explicit human "yes".
2. :class:`ConfirmationGuardrail` — a Strands hook provider that cancels any
   consequential tool call unless a one-shot grant was recorded (by the
   frontend/console once it collects the user's confirmation).

The agent is *also* instructed by the persona to ask before these actions;
the hook is the hard backstop, not the UX.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strands.experimental.hooks.events import BidiBeforeToolCallEvent
from strands.hooks import BeforeToolCallEvent, HookRegistry

# Stage advancements that close out a turnover.
_CONSEQUENTIAL_STAGES = {"DONE", "REPORT"}


def requires_confirmation(tool_name: str, tool_input: Mapping[str, Any] | None = None) -> bool:
    """True when a tool call must be explicitly confirmed by a human first.

    Policy: URGENT work orders, advancing a task to DONE/REPORT, and any
    report delivery (owner comms) always need confirmation.
    """
    tool_input = tool_input or {}
    if tool_name == "deliver_report":
        return True
    if tool_name == "open_work_order":
        return str(tool_input.get("priority", "MEDIUM")).strip().upper() == "URGENT"
    if tool_name == "advance_stage":
        return str(tool_input.get("stage_key", "")).strip().upper() in _CONSEQUENTIAL_STAGES
    return False


class ConfirmationGuardrail:
    """Hook provider cancelling unconfirmed consequential tool calls.

    Grants are one-shot: ``grant("deliver_report")`` allows exactly the next
    ``deliver_report`` call through, then expires.
    """

    def __init__(self) -> None:
        self._granted: set[str] = set()

    def grant(self, tool_name: str) -> None:
        """Record a one-shot human confirmation for a tool."""
        self._granted.add(tool_name)

    def revoke(self, tool_name: str) -> None:
        """Withdraw a previously recorded confirmation."""
        self._granted.discard(tool_name)

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        """Register the before-tool-call check for both agent runtimes."""
        registry.add_callback(BeforeToolCallEvent, self.check)
        registry.add_callback(BidiBeforeToolCallEvent, self.check)

    def check(self, event: Any) -> None:
        """Cancel the tool call unless it is confirmed or non-consequential."""
        name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}
        if not requires_confirmation(name, tool_input):
            return
        if name in self._granted:
            self._granted.discard(name)
            return
        event.cancel_tool = (
            f"'{name}' is a consequential action and needs explicit user confirmation. "
            "Tell the user exactly what you intend to do and ask for a yes; the call "
            "will be allowed once confirmation is granted."
        )
