from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

from app import _vendor  # noqa: F401  (select the vendored bidi harness)
from strands import tool
from strands.experimental.bidi import (
    BidiAgent,
    BidiResponseCompleteEvent,
    BidiResponseStartEvent,
    ToolUseStreamEvent,
)
from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel
from strands_tools import load_tool
from google.genai.types import LiveServerContent, LiveServerMessage


class RecordingBidiModel:
    """Deterministic transport for exercising the real vendored bidi loop."""

    config: dict[str, Any] = {}

    def __init__(self) -> None:
        self.start_calls: list[dict[str, Any]] = []
        self.stop_calls = 0
        self.sent: list[Any] = []
        self._events: asyncio.Queue[Any] = asyncio.Queue()
        self._stop_receive = object()

    async def start(
        self,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        self.start_calls.append(
            {
                "system_prompt": system_prompt,
                "tools": tools,
                "messages": messages,
                "kwargs": kwargs,
            }
        )

    async def stop(self) -> None:
        self.stop_calls += 1
        await self._events.put(self._stop_receive)

    async def send(self, content: Any) -> None:
        self.sent.append(content)

    async def receive(self) -> AsyncGenerator[Any, None]:
        while True:
            event = await self._events.get()
            if event is self._stop_receive:
                return
            yield event

    async def emit(self, event: Any) -> None:
        await self._events.put(event)


class RestartCloseErrorModel(RecordingBidiModel):
    """Provider whose old receive stream errors when an intentional stop closes it."""

    async def start(self, *args: Any, **kwargs: Any) -> None:
        self._events = asyncio.Queue()
        await super().start(*args, **kwargs)

    async def receive(self) -> AsyncGenerator[Any, None]:
        events = self._events
        while True:
            event = await events.get()
            if event is self._stop_receive:
                raise RuntimeError("provider receive closed during intentional restart")
            yield event


def _write_tool(path: Path, name: str) -> None:
    path.write_text(
        "from strands import tool\n\n"
        "@tool\n"
        f"def {name}() -> str:\n"
        f'    """Return from {name}."""\n'
        f'    return "{name}"\n'
    )


async def _wait_until(predicate: Any, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_loaded_tools_restart_once_after_turn_and_preserve_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BYPASS_TOOL_CONSENT", "true")
    first_path = tmp_path / "first_dynamic.py"
    second_path = tmp_path / "second_dynamic.py"
    _write_tool(first_path, "first_dynamic")
    _write_tool(second_path, "second_dynamic")

    model = RestartCloseErrorModel()
    initial_message = {"role": "user", "content": [{"text": "load both tools"}]}
    agent = BidiAgent(
        model=model,
        tools=[load_tool.load_tool],
        messages=[initial_message],
        system_prompt="test prompt",
    )
    await agent.start()

    received: list[dict[str, Any]] = []

    async def receive_until_tools_updated() -> None:
        async for event in agent.receive():
            received.append(dict(event))
            if event.get("type") == "bidi_tools_updated":
                return

    receiver = asyncio.create_task(receive_until_tools_updated())
    try:
        await model.emit(
            ToolUseStreamEvent(
                delta={},
                current_tool_use={
                    "toolUseId": "load-1",
                    "name": "load_tool",
                    "input": {"name": "first_dynamic", "path": str(first_path)},
                },
            )
        )
        await model.emit(
            ToolUseStreamEvent(
                delta={},
                current_tool_use={
                    "toolUseId": "load-2",
                    "name": "load_tool",
                    "input": {"name": "second_dynamic", "path": str(second_path)},
                },
            )
        )
        await _wait_until(lambda: {"first_dynamic", "second_dynamic"} <= set(agent.tool_names))

        assert len(model.start_calls) == 1
        await model.emit(BidiResponseCompleteEvent(response_id="response-1", stop_reason="tool_use"))
        await asyncio.wait_for(receiver, timeout=2)
        await asyncio.sleep(0.05)

        assert len(model.start_calls) == 2
        assert model.stop_calls == 1
        restarted = model.start_calls[1]
        assert restarted["messages"] is agent.messages
        assert initial_message in restarted["messages"]
        assert len(restarted["messages"]) == 5
        assert {spec["name"] for spec in restarted["tools"]} == {
            "load_tool",
            "first_dynamic",
            "second_dynamic",
        }
        assert received[-1] == {
            "type": "bidi_tools_updated",
            "tools": ["first_dynamic", "load_tool", "second_dynamic"],
        }

        next_event = asyncio.create_task(anext(agent.receive()))
        await model.emit(BidiResponseStartEvent(response_id="after-restart"))
        assert await asyncio.wait_for(next_event, timeout=2) == {
            "type": "bidi_response_start",
            "response_id": "after-restart",
        }
    finally:
        if not receiver.done():
            receiver.cancel()
        await agent.stop()


@tool
def unchanged_tool() -> str:
    """Return without changing the registry."""
    return "unchanged"


@pytest.mark.asyncio
async def test_registry_unchanged_does_not_restart() -> None:
    model = RecordingBidiModel()
    agent = BidiAgent(model=model, tools=[unchanged_tool])
    await agent.start()

    received_types: list[str] = []

    async def receive_until_complete() -> None:
        async for event in agent.receive():
            if event_type := event.get("type"):
                received_types.append(event_type)
            if event_type == "bidi_response_complete":
                return

    receiver = asyncio.create_task(receive_until_complete())
    try:
        await model.emit(
            ToolUseStreamEvent(
                delta={},
                current_tool_use={
                    "toolUseId": "unchanged-1",
                    "name": "unchanged_tool",
                    "input": {},
                },
            )
        )
        await model.emit(BidiResponseCompleteEvent(response_id="response-1", stop_reason="tool_use"))
        await asyncio.wait_for(receiver, timeout=2)
        await _wait_until(lambda: len(agent.messages) == 2)
        await asyncio.sleep(0.05)

        assert len(model.start_calls) == 1
        assert model.stop_calls == 0
        assert "bidi_tools_updated" not in received_types
    finally:
        await agent.stop()


def test_gemini_turn_complete_is_a_restart_safe_boundary() -> None:
    model = object.__new__(BidiGeminiLiveModel)
    events = model._convert_gemini_live_event(
        LiveServerMessage(server_content=LiveServerContent(turn_complete=True))
    )

    assert len(events) == 1
    assert events[0]["type"] == "bidi_response_complete"
    assert events[0]["stop_reason"] == "complete"


def test_gemini_graceful_restart_reuses_latest_resumption_handle() -> None:
    model = object.__new__(BidiGeminiLiveModel)
    model.config = {"inference": {}, "audio": {}}
    model._live_session_handle = "resume-handle"

    config = model._build_live_config()

    assert config["session_resumption"] == {"handle": "resume-handle"}
