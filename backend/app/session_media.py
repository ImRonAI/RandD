"""Session-isolated browser camera frames and recorded-clip mailboxes."""

from __future__ import annotations

import base64
import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Frame:
    ts: float
    jpeg: bytes


@dataclass
class _SessionState:
    frames: deque[Frame]
    clip: dict | None = None
    clip_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionMediaRegistry:
    """Keeps transient camera data isolated by authenticated session ID."""

    def __init__(self, max_frames: int = 10) -> None:
        self._max_frames = max_frames
        self._sessions: dict[str, _SessionState] = {}
        self._lock = threading.Lock()

    def _state(self, session_id: str) -> _SessionState:
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            return self._sessions.setdefault(
                session_id, _SessionState(frames=deque(maxlen=self._max_frames))
            )

    def add_frame(self, session_id: str, image_b64: str) -> None:
        try:
            jpeg = base64.b64decode(image_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid_camera_frame") from exc
        if not jpeg or len(jpeg) > 3 * 1024 * 1024:
            raise ValueError("invalid_camera_frame_size")
        state = self._state(session_id)
        with state.lock:
            state.frames.append(Frame(time.time(), jpeg))

    def latest_frame(self, session_id: str, max_age_seconds: float = 15.0) -> Frame | None:
        state = self._state(session_id)
        with state.lock:
            frame = state.frames[-1] if state.frames else None
        return frame if frame and time.time() - frame.ts <= max_age_seconds else None

    def frames_since(self, session_id: str, start_ts: float) -> list[Frame]:
        state = self._state(session_id)
        with state.lock:
            return [frame for frame in state.frames if frame.ts >= start_ts]

    def stream_active(self, session_id: str, max_age_seconds: float = 15.0) -> bool:
        return self.latest_frame(session_id, max_age_seconds) is not None

    def arm_clip(self, session_id: str) -> None:
        state = self._state(session_id)
        with state.lock:
            state.clip = None
            state.clip_event.clear()

    def deliver_clip(self, session_id: str, info: dict) -> None:
        if not isinstance(info, dict) or not info.get("path"):
            raise ValueError("invalid_clip_payload")
        state = self._state(session_id)
        with state.lock:
            state.clip = dict(info)
            state.clip_event.set()

    def wait_for_clip(self, session_id: str, timeout: float) -> dict | None:
        state = self._state(session_id)
        if not state.clip_event.wait(timeout):
            return None
        with state.lock:
            clip = state.clip
            state.clip = None
            state.clip_event.clear()
            return clip

    def discard(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
