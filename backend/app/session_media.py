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
    detection_sequence: int = 0
    latest_detections: dict | None = None
    detection_event: threading.Event = field(default_factory=threading.Event)
    detection_monitor_active: bool = False
    detection_history: deque[dict] = field(default_factory=lambda: deque(maxlen=500))
    detection_totals: dict[str, int] = field(default_factory=dict)
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

    def publish_detections(self, session_id: str, payload: dict, objects: dict[str, int]) -> None:
        """Publish the latest normalized YOLO boxes for one authenticated session."""
        state = self._state(session_id)
        with state.lock:
            state.detection_sequence += 1
            state.latest_detections = {
                **payload,
                "detections": [dict(item) for item in payload.get("detections", [])],
            }
            if objects:
                state.detection_history.append(
                    {"ts": float(payload.get("timestamp", time.time())), "objects": dict(sorted(objects.items()))}
                )
                for label, count in objects.items():
                    state.detection_totals[label] = max(state.detection_totals.get(label, 0), count)
            state.detection_event.set()

    def wait_for_detections(
        self,
        session_id: str,
        after_sequence: int,
        timeout: float,
    ) -> tuple[int, dict] | None:
        """Wait for a detection payload newer than ``after_sequence``."""
        state = self._state(session_id)
        if not state.detection_event.wait(timeout):
            return None
        with state.lock:
            if state.detection_sequence <= after_sequence or state.latest_detections is None:
                state.detection_event.clear()
                return None
            sequence = state.detection_sequence
            payload = {
                **state.latest_detections,
                "detections": [dict(item) for item in state.latest_detections.get("detections", [])],
            }
            state.detection_event.clear()
            return sequence, payload

    def start_detection_monitor(self, session_id: str) -> bool:
        state = self._state(session_id)
        with state.lock:
            if state.detection_monitor_active:
                return False
            state.detection_monitor_active = True
            state.detection_history.clear()
            state.detection_totals.clear()
            return True

    def stop_detection_monitor(self, session_id: str) -> None:
        state = self._state(session_id)
        with state.lock:
            state.detection_monitor_active = False

    def detection_monitor_active(self, session_id: str) -> bool:
        state = self._state(session_id)
        with state.lock:
            return state.detection_monitor_active

    def detection_status(self, session_id: str) -> dict:
        state = self._state(session_id)
        with state.lock:
            return {
                "active": state.detection_monitor_active,
                "totals": dict(sorted(state.detection_totals.items())),
                "recent": [
                    {"ts": entry["ts"], "objects": dict(entry["objects"])}
                    for entry in list(state.detection_history)[-5:]
                ],
            }

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
