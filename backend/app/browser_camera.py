"""Authenticated-session bridge between browser camera streams and tools."""

from __future__ import annotations

from contextvars import ContextVar, Token
from contextlib import contextmanager
from dataclasses import dataclass
import time

from app.session_media import Frame, SessionMediaRegistry

_session_id: ContextVar[str | None] = ContextVar("browser_camera_session_id", default=None)
_registry = SessionMediaRegistry(max_frames=10)


def bind_session(session_id: str) -> Token:
    if not session_id:
        raise ValueError("authenticated session_id is required")
    return _session_id.set(session_id)


def unbind_session(token: Token) -> None:
    _session_id.reset(token)


@contextmanager
def session_scope(session_id: str):
    """Integration hook for a WebSocket message/HTTP upload authenticated session."""
    token = bind_session(session_id)
    try:
        yield
    finally:
        unbind_session(token)


def current_session_id() -> str:
    session_id = _session_id.get()
    if not session_id:
        raise RuntimeError("camera_session_unbound")
    return session_id


def add_frame(image_b64: str) -> None:
    _registry.add_frame(current_session_id(), image_b64)


def latest_frame(max_age_seconds: float = 15.0) -> Frame | None:
    return _registry.latest_frame(current_session_id(), max_age_seconds)


def wait_for_frame(
    timeout_seconds: float = 5.0,
    max_age_seconds: float = 15.0,
    poll_interval: float = 0.05,
) -> Frame | None:
    """Wait briefly for the browser's asynchronous camera startup to yield a frame."""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        frame = latest_frame(max_age_seconds)
        if frame is not None:
            return frame
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(max(0.01, poll_interval), remaining))


def frames_since(start_ts: float) -> list[Frame]:
    return _registry.frames_since(current_session_id(), start_ts)


def stream_active(max_age_seconds: float = 15.0) -> bool:
    return _registry.stream_active(current_session_id(), max_age_seconds)


def arm_clip_capture() -> None:
    _registry.arm_clip(current_session_id())


def deliver_clip(info: dict) -> None:
    _registry.deliver_clip(current_session_id(), info)


def wait_for_clip(timeout: float) -> dict | None:
    return _registry.wait_for_clip(current_session_id(), timeout)


def discard_session(session_id: str) -> None:
    """WebSocket teardown hook; session ID must come from authenticated server state."""
    if session_id != current_session_id():
        raise PermissionError("cannot discard another camera session")
    _registry.discard(session_id)
