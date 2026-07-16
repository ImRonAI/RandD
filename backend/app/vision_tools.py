"""YOLO object detection over the INSPECTOR'S DEVICE CAMERA stream.

Runs ultralytics YOLO against the browser-camera frames teed into
``app.browser_camera`` (any phone/tablet/laptop camera the inspector uses),
falling back to server-attached cameras when no stream is live. Supports
one-shot detection and a continuous background monitor for walkthroughs.
"""

import threading
import time
from collections import defaultdict
from typing import Any, Dict

from strands import tool

from app import browser_camera

_lock = threading.Lock()
_monitor_thread: threading.Thread | None = None
_monitor_active = False
_history: list[dict] = []  # [{ts, objects: {label: count}}]
_totals: dict[str, int] = defaultdict(int)
_model = None


def _load_model(model_name: str = "yolov8n.pt"):
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(model_name)
    return _model


def _detect_jpeg(jpeg: bytes, confidence: float) -> dict[str, int]:
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {}
    model = _load_model()
    results = model(img, conf=confidence, verbose=False)
    objects: dict[str, int] = defaultdict(int)
    for result in results:
        for box in result.boxes:
            objects[model.names[int(box.cls[0])]] += 1
    return dict(objects)


def _monitor_worker(confidence: float, interval: float) -> None:
    global _monitor_active
    last_ts = 0.0
    while _monitor_active:
        frame = browser_camera.latest_frame()
        if frame and frame.ts > last_ts:
            last_ts = frame.ts
            try:
                objects = _detect_jpeg(frame.jpeg, confidence)
            except Exception:
                objects = {}
            if objects:
                with _lock:
                    _history.append({"ts": frame.ts, "objects": objects})
                    if len(_history) > 500:
                        del _history[:100]
                    for label, count in objects.items():
                        _totals[label] = max(_totals[label], count)
        time.sleep(interval)


@tool
def yolo_vision(action: str = "detect", confidence: float = 0.4, interval: float = 2.0) -> Dict[str, Any]:
    """Detect objects in the inspector's device-camera view with YOLO.

    Works on the live browser camera stream from ANY device (phone, tablet,
    laptop) — start the camera first with control_camera("start").

    Args:
        action: "detect" = analyze the current view once;
            "start" = begin continuous background monitoring of the walkthrough;
            "stop" = end monitoring; "status" = monitoring summary so far.
        confidence: Detection confidence threshold (0.1-0.9).
        interval: Seconds between checks while monitoring.

    Returns:
        Dict with status and detected objects.
    """
    global _monitor_thread, _monitor_active
    try:
        confidence = max(0.1, min(float(confidence), 0.9))
        action = action.strip().lower()

        if action == "detect":
            frame = browser_camera.wait_for_frame()
            if frame is None:
                return {
                    "status": "error",
                    "content": [{"text": '❌ No live camera stream — call control_camera("start") first.'}],
                }
            objects = _detect_jpeg(frame.jpeg, confidence)
            if not objects:
                return {"status": "success", "content": [{"text": "👁 No objects detected in the current view."}]}
            listing = ", ".join(f"{label} ×{count}" for label, count in sorted(objects.items()))
            return {"status": "success", "content": [{"text": f"👁 Current view: {listing}"}]}

        if action == "start":
            if _monitor_active:
                return {"status": "success", "content": [{"text": "👁 Monitoring already running."}]}
            if browser_camera.wait_for_frame() is None:
                return {
                    "status": "error",
                    "content": [{"text": '❌ No live camera stream — call control_camera("start") first.'}],
                }
            _load_model()  # fail fast if weights unavailable
            _monitor_active = True
            _monitor_thread = threading.Thread(
                target=_monitor_worker, args=(confidence, max(0.5, float(interval))), daemon=True
            )
            _monitor_thread.start()
            return {"status": "success", "content": [{"text": f"👁 Continuous detection started (conf {confidence}, every {interval}s)."}]}

        if action == "stop":
            _monitor_active = False
            with _lock:
                summary = ", ".join(f"{label} (max {count})" for label, count in sorted(_totals.items())) or "nothing detected"
            return {"status": "success", "content": [{"text": f"👁 Monitoring stopped. Seen this session: {summary}."}]}

        if action == "status":
            with _lock:
                recent = _history[-5:]
                summary = ", ".join(f"{label} (max {count})" for label, count in sorted(_totals.items())) or "nothing yet"
            lines = [f"👁 Monitoring {'ACTIVE' if _monitor_active else 'inactive'} — totals: {summary}"]
            for entry in recent:
                listing = ", ".join(f"{label} ×{count}" for label, count in entry["objects"].items())
                lines.append(f"  {time.strftime('%H:%M:%S', time.localtime(entry['ts']))}: {listing}")
            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        return {"status": "error", "content": [{"text": f"Unknown action {action!r} — use detect, start, stop, or status."}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Vision error: {e}"}]}
