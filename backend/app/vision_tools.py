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

_model = None
_model_lock = threading.Lock()


def _load_model(model_name: str = "yolov8n.pt"):
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(model_name)
    return _model


def _serialize_result(result: Any) -> dict[str, Any]:
    """Serialize official Ultralytics ``Results.boxes`` into normalized UI metadata."""
    def values(data: Any) -> list[Any]:
        if hasattr(data, "cpu"):
            data = data.cpu()
        return data.tolist()

    coordinates = values(result.boxes.xyxyn)
    confidences = values(result.boxes.conf)
    class_ids = values(result.boxes.cls)
    detections = []
    objects: dict[str, int] = defaultdict(int)
    for box, score, class_id in zip(coordinates, confidences, class_ids, strict=True):
        label = result.names[int(class_id)]
        detections.append(
            {
                "x1": float(box[0]),
                "y1": float(box[1]),
                "x2": float(box[2]),
                "y2": float(box[3]),
                "confidence": float(score),
                "classId": int(class_id),
                "label": label,
            }
        )
        objects[label] += 1
    height, width = result.orig_shape
    return {
        "width": int(width),
        "height": int(height),
        "detections": detections,
        "objects": dict(sorted(objects.items())),
    }


def _detect_jpeg(jpeg: bytes, confidence: float) -> dict[str, Any]:
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"width": 0, "height": 0, "detections": [], "objects": {}}
    model = _load_model()
    with _model_lock:
        result = model(img, conf=confidence, verbose=False)[0]
    return _serialize_result(result)


def _publish_analysis(frame_ts: float, analysis: dict[str, Any]) -> None:
    browser_camera.publish_detections(
        {
            "type": "yolo_detections",
            "timestamp": frame_ts,
            "width": analysis["width"],
            "height": analysis["height"],
            "detections": analysis["detections"],
        },
        analysis["objects"],
    )


def _monitor_worker(session_id: str, confidence: float, interval: float) -> None:
    with browser_camera.session_scope(session_id):
        last_ts = 0.0
        while browser_camera.detection_monitor_active():
            frame = browser_camera.latest_frame()
            if frame and frame.ts > last_ts:
                last_ts = frame.ts
                try:
                    analysis = _detect_jpeg(frame.jpeg, confidence)
                except Exception:
                    analysis = {"width": 0, "height": 0, "detections": [], "objects": {}}
                _publish_analysis(frame.ts, analysis)
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
            analysis = _detect_jpeg(frame.jpeg, confidence)
            _publish_analysis(frame.ts, analysis)
            objects = analysis["objects"]
            if not objects:
                return {"status": "success", "content": [{"text": "👁 No objects detected in the current view."}]}
            listing = ", ".join(f"{label} ×{count}" for label, count in sorted(objects.items()))
            return {"status": "success", "content": [{"text": f"👁 Current view: {listing}"}]}

        if action == "start":
            if browser_camera.detection_monitor_active():
                return {"status": "success", "content": [{"text": "👁 Monitoring already running."}]}
            if browser_camera.wait_for_frame() is None:
                return {
                    "status": "error",
                    "content": [{"text": '❌ No live camera stream — call control_camera("start") first.'}],
                }
            _load_model()  # fail fast if weights unavailable
            browser_camera.start_detection_monitor()
            session_id = browser_camera.current_session_id()
            monitor_thread = threading.Thread(
                target=_monitor_worker,
                args=(session_id, confidence, max(0.5, float(interval))),
                daemon=True,
            )
            monitor_thread.start()
            return {"status": "success", "content": [{"text": f"👁 Continuous detection started (conf {confidence}, every {interval}s)."}]}

        if action == "stop":
            status = browser_camera.detection_status()
            browser_camera.stop_detection_monitor()
            _publish_analysis(time.time(), {"width": 0, "height": 0, "detections": [], "objects": {}})
            summary = ", ".join(f"{label} (max {count})" for label, count in status["totals"].items()) or "nothing detected"
            return {"status": "success", "content": [{"text": f"👁 Monitoring stopped. Seen this session: {summary}."}]}

        if action == "status":
            status = browser_camera.detection_status()
            summary = ", ".join(f"{label} (max {count})" for label, count in status["totals"].items()) or "nothing yet"
            lines = [f"👁 Monitoring {'ACTIVE' if status['active'] else 'inactive'} — totals: {summary}"]
            for entry in status["recent"]:
                listing = ", ".join(f"{label} ×{count}" for label, count in entry["objects"].items())
                lines.append(f"  {time.strftime('%H:%M:%S', time.localtime(entry['ts']))}: {listing}")
            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        return {"status": "error", "content": [{"text": f"Unknown action {action!r} — use detect, start, stop, or status."}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Vision error: {e}"}]}
