"""Record video using camera with multi-camera support.

Modeled directly on strands_fun_tools.take_photo — same discovery, validation,
parallel-capture, and result-formatting structure — with the single-frame
capture replaced by an OpenCV VideoWriter recording loop.

IMPORTANT deployment note: like take_photo, this records cameras attached to
the SERVER running the agent. The inspector's phone/tablet/laptop camcorder
lives in their browser — that path streams via getUserMedia in the frontend
(see frontend/src/lib/camera.ts), not through this tool.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from strands import tool


def _discover_cameras(max_check: int = 10) -> List[int]:
    """Discover all available cameras by checking indices."""
    available_cameras = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available_cameras.append(i)
            cap.release()
    return available_cameras


def _record_from_camera(
    camera_id: int,
    save_dir: Path,
    duration: float,
    fps: float,
    delay: float,
) -> Dict[str, Any]:
    """Record a single video clip from a specific camera."""
    try:
        cam = cv2.VideoCapture(camera_id)
        if not cam.isOpened():
            return {
                "camera_id": camera_id,
                "status": "error",
                "message": "Failed to open camera",
            }

        # Warmup and delay
        time.sleep(delay)
        ret, frame = cam.read()
        if not ret:
            cam.release()
            return {
                "camera_id": camera_id,
                "status": "error",
                "message": "Failed to capture frame",
            }

        height, width = frame.shape[:2]

        # Save video with meaningful filename
        timestamp = int(time.time())
        filename = f"video-{timestamp}-cam{camera_id}-{int(duration)}s.mp4"
        filepath = save_dir / filename

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(filepath), fourcc, fps, (width, height))
        if not writer.isOpened():
            cam.release()
            return {
                "camera_id": camera_id,
                "status": "error",
                "message": "Failed to open video writer",
            }

        frames_written = 0
        frame_interval = 1.0 / fps
        end_time = time.monotonic() + duration
        next_frame_at = time.monotonic()
        writer.write(frame)
        frames_written += 1

        while time.monotonic() < end_time:
            next_frame_at += frame_interval
            ret, frame = cam.read()
            if not ret:
                break
            writer.write(frame)
            frames_written += 1
            sleep_for = next_frame_at - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

        writer.release()
        cam.release()

        file_size = os.path.getsize(filepath)

        return {
            "camera_id": camera_id,
            "status": "success",
            "filepath": str(filepath),
            "resolution": f"{width}x{height}",
            "duration_seconds": round(frames_written / fps, 1),
            "frames": frames_written,
            "fps": fps,
            "file_size": file_size,
        }

    except Exception as e:
        return {"camera_id": camera_id, "status": "error", "message": str(e)}


@tool
def take_video(
    camera_ids: Optional[List[int]] = None,
    duration: float = 5.0,
    fps: float = 15.0,
    delay: float = 3.0,
    save_path: str = None,
    discover: bool = False,
) -> Dict[str, Any]:
    """Record video clips using computer's camera(s) with multi-camera support

    Args:
        camera_ids: List of camera IDs to use (e.g., [0, 1, 2]). If None, uses camera 0
        duration: Length of each clip in seconds (1-120)
        fps: Frames per second to record (1-60)
        delay: Delay before recording starts in seconds
        save_path: Directory to save videos (defaults to current directory)
        discover: If True, discover and list all available cameras without recording

    Returns:
        Dict with status and content
    """
    try:
        # Discovery mode
        if discover:
            cameras = _discover_cameras()
            if not cameras:
                return {
                    "status": "error",
                    "content": [{"text": "❌ No cameras detected"}],
                }

            result_info = [
                "🔍 **Camera Discovery Results:**",
                f"Found {len(cameras)} camera(s): {cameras}",
                "",
                "Use `camera_ids=[0, 1, 2]` to record from specific cameras",
            ]
            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        # Clamp inputs
        duration = max(1.0, min(float(duration), 120.0))
        fps = max(1.0, min(float(fps), 60.0))

        # Setup save directory
        save_dir = Path(save_path).expanduser() if save_path else Path.cwd()
        save_dir.mkdir(parents=True, exist_ok=True)

        # Determine which cameras to use
        if camera_ids is None:
            camera_ids = [0]  # Default to camera 0

        # Validate cameras exist
        available = _discover_cameras()
        for cam_id in camera_ids:
            if cam_id not in available:
                return {
                    "status": "error",
                    "content": [
                        {"text": f"❌ Camera {cam_id} not available. Available: {available}"}
                    ],
                }

        all_results = []
        successful_recordings = 0

        # Multi-camera parallel recording
        if len(camera_ids) > 1:
            print(f"🎥 Recording from {len(camera_ids)} cameras in parallel...")

            with ThreadPoolExecutor(max_workers=len(camera_ids)) as executor:
                futures = [
                    executor.submit(
                        _record_from_camera, cam_id, save_dir, duration, fps, delay
                    )
                    for cam_id in camera_ids
                ]
                for future in as_completed(futures):
                    result = future.result()
                    all_results.append(result)
                    if result["status"] == "success":
                        successful_recordings += 1

        # Single camera recording
        else:
            cam_id = camera_ids[0]
            print(f"🎥 Recording {duration}s from camera {cam_id}...")
            result = _record_from_camera(cam_id, save_dir, duration, fps, delay)
            all_results.append(result)
            if result["status"] == "success":
                successful_recordings += 1

        # Format results
        result_info = [
            "🎥 **Video Recording Results:**",
            f"✅ Success: {successful_recordings}/{len(all_results)} clips",
            f"📁 Save directory: `{save_dir}`",
            "",
        ]

        for result in all_results:
            if result["status"] == "success":
                result_info.append(
                    f"✅ **Camera {result['camera_id']}**: {result['resolution']} "
                    f"({result['duration_seconds']}s @ {result['fps']}fps, "
                    f"{result['file_size']:,} bytes) → `{result['filepath']}`"
                )
            else:
                result_info.append(
                    f"❌ **Camera {result['camera_id']}**: {result['message']}"
                )

        status = "success" if successful_recordings > 0 else "error"
        return {"status": status, "content": [{"text": "\n".join(result_info)}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Video error: {str(e)}"}]}
