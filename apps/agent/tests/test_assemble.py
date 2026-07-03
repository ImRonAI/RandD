"""Agent assembly with an injected fake BidiModel (no network), plus persona."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any

from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models.model import BidiModel

from strqc_agent.assemble import build_agent
from strqc_agent.persona import PERSONA_VERSION, SYSTEM_PROMPT, build_system_prompt
from strqc_agent.tools.slack_delivery import DryRunDelivery

EXPECTED_TOOLS = {
    "list_checklist_items",
    "record_checklist_result",
    "capture_photo",
    "open_work_order",
    "list_open_work_orders",
    "advance_stage",
    "get_property_brief",
    "deliver_report",
}


class FakeBidiModel:
    """Duck-typed BidiModel — never touches the network."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = {}

    async def start(self, system_prompt=None, tools=None, messages=None, **kwargs) -> None:
        pass

    async def stop(self) -> None:
        pass

    def receive(self) -> AsyncIterable:
        async def _empty():
            return
            yield

        return _empty()

    async def send(self, content) -> None:
        pass


def test_fake_model_satisfies_protocol():
    assert isinstance(FakeBidiModel(), BidiModel)


def test_build_agent_registers_all_tools(ctx):
    agent = build_agent(ctx, model=FakeBidiModel(), delivery=DryRunDelivery())
    assert isinstance(agent, BidiAgent)
    assert EXPECTED_TOOLS <= set(agent.tool_names)


def test_build_agent_prompt_carries_persona_and_property_context(ctx):
    agent = build_agent(ctx, model=FakeBidiModel(), delivery=DryRunDelivery())
    assert f"[persona v{PERSONA_VERSION}]" in agent.system_prompt
    assert "BBL-014" in agent.system_prompt
    assert "Hot tub cover straps" in agent.system_prompt
    # Secrets never end up in the prompt.
    assert "ciphertext" not in agent.system_prompt


def test_build_system_prompt_without_context_is_base():
    assert build_system_prompt() == SYSTEM_PROMPT
    assert build_system_prompt(None) == SYSTEM_PROMPT
    appended = build_system_prompt("Property: X")
    assert appended.startswith(SYSTEM_PROMPT)
    assert "Property: X" in appended
