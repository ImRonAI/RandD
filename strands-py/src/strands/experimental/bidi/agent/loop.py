"""Agent loop.

The agent loop handles the events received from the model and executes tools when given a tool use request.
"""

import asyncio
import logging
import warnings
from typing import TYPE_CHECKING, Any, AsyncGenerator, cast

from ....types._events import ToolInterruptEvent, ToolResultEvent, ToolResultMessageEvent, ToolUseStreamEvent
from ....types.content import Message
from ....types.tools import ToolResult, ToolUse
from ...hooks.events import (
    BidiAfterConnectionRestartEvent,
    BidiAfterToolCallEvent,
    BidiAfterInvocationEvent,
    BidiBeforeConnectionRestartEvent,
    BidiBeforeInvocationEvent,
)
from ...hooks.events import (
    BidiInterruptionEvent as BidiInterruptionHookEvent,
)
from .._async import _TaskPool, stop_all
from ..models import BidiModelTimeoutError
from ..types.events import (
    BidiConnectionCloseEvent,
    BidiConnectionRestartEvent,
    BidiInputEvent,
    BidiInterruptionEvent,
    BidiOutputEvent,
    BidiResponseCompleteEvent,
    BidiResponseStartEvent,
    BidiTextInputEvent,
    BidiToolsUpdatedEvent,
    BidiTranscriptStreamEvent,
)

if TYPE_CHECKING:
    from .agent import BidiAgent

logger = logging.getLogger(__name__)
_TOOLS_CHANGED = object()


class _BidiAgentLoop:
    """Agent loop.

    Attributes:
        _agent: BidiAgent instance to loop.
        _started: Flag if agent loop has started.
        _task_pool: Track active async tasks created in loop.
        _event_queue: Queue model and tool call events for receiver.
        _invocation_state: Optional context to pass to tools during execution.
            This allows passing custom data (user_id, session_id, database connections, etc.)
            that tools can access via their invocation_state parameter.
        _send_gate: Gate the sending of events to the model.
            Blocks when agent is reseting the model connection after timeout.
    """

    def __init__(self, agent: "BidiAgent") -> None:
        """Initialize members of the agent loop.

        Note, before receiving events from the loop, the user must call `start`.

        Args:
            agent: Bidirectional agent to loop over.
        """
        self._agent = agent
        self._started = False
        self._task_pool = _TaskPool()
        self._event_queue: asyncio.Queue
        self._invocation_state: dict[str, Any]

        self._send_gate = asyncio.Event()
        self._restart_lock = asyncio.Lock()
        self._declared_tool_names: set[str] = set()
        self._tools_restart_pending = False
        self._tools_restart_queued = False
        self._turn_in_progress = False
        self._active_tool_calls = 0
        self._model_generation = 0
        self._agent.hooks.add_callback(BidiAfterToolCallEvent, self._after_tool_call)

    async def start(self, invocation_state: dict[str, Any] | None = None) -> None:
        """Start the agent loop.

        The agent model is started as part of this call.

        Args:
            invocation_state: Optional context to pass to tools during execution.
                This allows passing custom data (user_id, session_id, database connections, etc.)
                that tools can access via their invocation_state parameter.

        Raises:
            RuntimeError: If loop already started.
        """
        if self._started:
            raise RuntimeError("loop already started | call stop before starting again")

        logger.debug("agent loop starting")
        await self._agent.hooks.invoke_callbacks_async(BidiBeforeInvocationEvent(agent=self._agent))

        tool_specs = self._agent.tool_registry.get_all_tool_specs()
        await self._agent.model.start(
            system_prompt=self._agent.system_prompt,
            tools=tool_specs,
            messages=self._agent.messages,
        )
        self._declared_tool_names = {spec["name"] for spec in tool_specs}

        self._event_queue = asyncio.Queue(maxsize=1)

        self._task_pool = _TaskPool()
        self._model_generation += 1
        self._task_pool.create(self._run_model(self._model_generation))

        self._invocation_state = invocation_state or {}
        self._send_gate.set()
        self._started = True

    async def stop(self) -> None:
        """Stop the agent loop."""
        logger.debug("agent loop stopping")

        self._started = False
        self._send_gate.clear()
        self._invocation_state = {}

        async def stop_tasks() -> None:
            await self._task_pool.cancel()

        async def stop_model() -> None:
            await self._agent.model.stop()

        try:
            await stop_all(stop_tasks, stop_model)
        finally:
            await self._agent.hooks.invoke_callbacks_async(BidiAfterInvocationEvent(agent=self._agent))

    async def send(self, event: BidiInputEvent | ToolResultEvent) -> None:
        """Send model event.

        Additionally, add text input to messages array.

        Args:
            event: User input event or tool result.

        Raises:
            RuntimeError: If start has not been called.
        """
        if not self._started:
            raise RuntimeError("loop not started | call start before sending")

        if not self._send_gate.is_set():
            logger.debug("waiting for model send signal")
            await self._send_gate.wait()

        if isinstance(event, BidiTextInputEvent):
            message: Message = {"role": event.role, "content": [{"text": event.text}]}
            await self._agent._append_messages(message)

        await self._agent.model.send(event)

    async def receive(self) -> AsyncGenerator[BidiOutputEvent, None]:
        """Receive model and tool call events.

        Returns:
            Model and tool call events.

        Raises:
            RuntimeError: If start has not been called.
        """
        if not self._started:
            raise RuntimeError("loop not started | call start before receiving")

        while True:
            event = await self._event_queue.get()
            if isinstance(event, BidiModelTimeoutError):
                logger.debug("model timeout error received")
                yield BidiConnectionRestartEvent(event)
                previous_tool_names = self._declared_tool_names
                await self._restart_connection(event)
                if self._tools_restart_pending and self._declared_tool_names != previous_tool_names:
                    self._tools_restart_pending = False
                    self._tools_restart_queued = False
                    yield BidiToolsUpdatedEvent(sorted(self._declared_tool_names))
                continue

            if event is _TOOLS_CHANGED:
                restart_exception, restarted = await self._restart_connection(require_tool_growth=True)
                self._tools_restart_pending = False
                self._tools_restart_queued = False
                if restart_exception is not None:
                    raise restart_exception
                if restarted:
                    yield BidiToolsUpdatedEvent(sorted(self._declared_tool_names))
                continue

            if isinstance(event, Exception):
                raise event

            # Check for graceful shutdown event
            if isinstance(event, BidiConnectionCloseEvent) and event.reason == "user_request":
                yield event
                break

            yield event

    async def _restart_connection(
        self,
        timeout_error: BidiModelTimeoutError | None = None,
        *,
        require_tool_growth: bool = False,
    ) -> tuple[Exception | None, bool]:
        """Restart the model connection using the shared graceful restart path.

        Args:
            timeout_error: Optional timeout error reported by the model.
            require_tool_growth: Skip the restart if the current registry has no
                names that were absent from the last model declaration.

        Returns:
            The restart exception, if any, and whether a restart was attempted.
        """
        async with self._restart_lock:
            tool_specs = self._agent.tool_registry.get_all_tool_specs()
            tool_names = {spec["name"] for spec in tool_specs}
            if require_tool_growth and not tool_names.difference(self._declared_tool_names):
                return None, False

            logger.debug("reseting model connection")

            self._send_gate.clear()

            if timeout_error is not None:
                await self._agent.hooks.invoke_callbacks_async(
                    BidiBeforeConnectionRestartEvent(self._agent, timeout_error)
                )

            restart_exception = None
            self._model_generation += 1
            restart_generation = self._model_generation
            try:
                await self._agent.model.stop()
                await self._agent.model.start(
                    self._agent.system_prompt,
                    tool_specs,
                    self._agent.messages,
                    **(timeout_error.restart_config if timeout_error is not None else {}),
                )
                self._declared_tool_names = tool_names
                self._task_pool.create(self._run_model(restart_generation))
            except Exception as exception:
                restart_exception = exception
            finally:
                if timeout_error is not None:
                    await self._agent.hooks.invoke_callbacks_async(
                        BidiAfterConnectionRestartEvent(self._agent, restart_exception)
                    )

            self._send_gate.set()
            return restart_exception, True

    def _after_tool_call(self, event: BidiAfterToolCallEvent) -> None:
        """Mark successful load_tool registry growth for a turn-boundary restart."""
        if event.tool_use["name"] != "load_tool" or event.exception is not None:
            return

        current_names = {
            spec["name"] for spec in self._agent.tool_registry.get_all_tool_specs()
        }
        if current_names.difference(self._declared_tool_names):
            self._tools_restart_pending = True

    async def _restart_for_updated_tools_if_ready(self) -> None:
        """Declare accumulated registry growth once the current turn is quiet."""
        if (
            not self._tools_restart_pending
            or self._tools_restart_queued
            or self._turn_in_progress
            or self._active_tool_calls
        ):
            return

        self._tools_restart_queued = True
        await self._event_queue.put(_TOOLS_CHANGED)

    async def _run_model(self, generation: int) -> None:
        """Task for running the model.

        Events are streamed through the event queue.
        """
        logger.debug("model task starting")

        try:
            async for event in self._agent.model.receive():
                if generation != self._model_generation:
                    return
                await self._event_queue.put(event)

                if isinstance(event, BidiResponseStartEvent):
                    self._turn_in_progress = True

                elif isinstance(event, BidiTranscriptStreamEvent):
                    if event["is_final"]:
                        message: Message = {"role": event["role"], "content": [{"text": event["text"]}]}
                        await self._agent._append_messages(message)

                elif isinstance(event, ToolUseStreamEvent):
                    self._turn_in_progress = True
                    tool_use = event["current_tool_use"]
                    self._active_tool_calls += 1
                    self._task_pool.create(self._run_tool(tool_use))

                elif isinstance(event, BidiResponseCompleteEvent):
                    self._turn_in_progress = False
                    await self._restart_for_updated_tools_if_ready()

                elif isinstance(event, BidiInterruptionEvent):
                    self._turn_in_progress = False
                    await self._agent.hooks.invoke_callbacks_async(
                        BidiInterruptionHookEvent(
                            agent=self._agent,
                            reason=event["reason"],
                            interrupted_response_id=event.get("interrupted_response_id"),
                        )
                    )
                    await self._restart_for_updated_tools_if_ready()

        except Exception as error:
            if generation == self._model_generation:
                await self._event_queue.put(error)
            else:
                logger.debug("ignoring stale model receive error during intentional restart", exc_info=error)

    async def _run_tool(self, tool_use: ToolUse) -> None:
        """Task for running tool requested by the model using the tool executor.

        Args:
            tool_use: Tool use request from model.
        """
        logger.debug("tool_name=<%s> | tool execution starting", tool_use["name"])

        tool_results: list[ToolResult] = []

        # Ensure request_state exists for tools like strands_tools.stop
        if "request_state" not in self._invocation_state:
            self._invocation_state["request_state"] = {}

        invocation_state: dict[str, Any] = {
            **self._invocation_state,
            "agent": self._agent,
            "model": self._agent.model,
            "messages": self._agent.messages,
            "system_prompt": self._agent.system_prompt,
        }

        try:
            tool_events = self._agent.tool_executor._stream(
                self._agent,
                tool_use,
                tool_results,
                invocation_state,
                structured_output_context=None,
            )

            async for tool_event in tool_events:
                if isinstance(tool_event, ToolInterruptEvent):
                    self._agent._interrupt_state.deactivate()
                    interrupt_names = [interrupt.name for interrupt in tool_event.interrupts]
                    raise RuntimeError(f"interrupts={interrupt_names} | tool interrupts are not supported in bidi")

                await self._event_queue.put(tool_event)

            # Normal flow for all tools (including stop_conversation)
            tool_result_event = cast(ToolResultEvent, tool_event)

            tool_use_message: Message = {"role": "assistant", "content": [{"toolUse": tool_use}]}
            tool_result_message: Message = {"role": "user", "content": [{"toolResult": tool_result_event.tool_result}]}
            await self._agent._append_messages(tool_use_message, tool_result_message)

            await self._event_queue.put(ToolResultMessageEvent(tool_result_message))

            # Check for stop_event_loop flag (set by strands_tools.stop, stop_conversation, or any custom tool)
            request_state = invocation_state.get("request_state", {})
            should_stop = request_state.get("stop_event_loop", False)

            # Backward compatibility: also check for stop_conversation by name (deprecated)
            if not should_stop and tool_use["name"] == "stop_conversation":
                warnings.warn(
                    "Stopping the event loop by tool name 'stop_conversation' is deprecated. "
                    "Use request_state['stop_event_loop'] = True instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                should_stop = True

            if should_stop:
                logger.info("stop_event_loop=<True> | stopping conversation")
                connection_id = getattr(self._agent.model, "_connection_id", "unknown")
                await self._event_queue.put(
                    BidiConnectionCloseEvent(connection_id=connection_id, reason="user_request")
                )
                return  # Skip sending result to model

            # Send result to model
            await self.send(tool_result_event)

        except Exception as error:
            await self._event_queue.put(error)
        finally:
            self._active_tool_calls -= 1
            await self._restart_for_updated_tools_if_ready()
