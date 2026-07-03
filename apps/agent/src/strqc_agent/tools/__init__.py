"""Strands tools for the STR QC agent (TASKS.md M3)."""

import logging
from importlib.util import find_spec
from pathlib import Path

from .camera import CaptureBackend, FileCaptureBackend, capture_photo, set_capture_backend
from .journal import list_checklist_items, record_checklist_result
from .property_info import get_property_brief
from .slack_delivery import (
    DeliveryAdapter,
    DryRunDelivery,
    SlackDelivery,
    deliver_report,
    make_delivery_adapter,
    set_delivery_adapter,
)
from .stages import advance_stage
from .work_orders import list_open_work_orders, open_work_order

logger = logging.getLogger(__name__)


def _vision_tool_paths() -> list[str]:
    """File paths for strands_fun_tools' take_photo / yolo_vision.

    Loaded by file path — NOT module path — because importing the
    strands_fun_tools package itself pulls in desktop-only deps (pyautogui)
    that crash in headless environments. Requires a working OpenCV
    (system libGL); if unavailable, the vision tools are skipped so the
    agent still assembles everywhere.
    """
    try:
        import cv2  # noqa: F401
    except Exception:  # pragma: no cover - depends on system libs
        logger.warning("OpenCV unavailable — take_photo/yolo_vision tools disabled")
        return []
    spec = find_spec("strands_fun_tools")
    if spec is None or not spec.submodule_search_locations:
        logger.warning("strands_fun_tools not installed — take_photo/yolo_vision tools disabled")
        return []
    base = Path(next(iter(spec.submodule_search_locations)))
    return [str(p) for p in (base / "take_photo.py", base / "yolo_vision.py") if p.exists()]


VISION_TOOL_PATHS = _vision_tool_paths()

ALL_TOOLS = [
    list_checklist_items,
    record_checklist_result,
    capture_photo,
    open_work_order,
    list_open_work_orders,
    advance_stage,
    get_property_brief,
    deliver_report,
    # Field vision (strands_fun_tools, loaded by file path): webcam capture
    # + continuous YOLO detection during walkthroughs.
    *VISION_TOOL_PATHS,
]

__all__ = [
    "ALL_TOOLS",
    "VISION_TOOL_PATHS",
    "CaptureBackend",
    "DeliveryAdapter",
    "DryRunDelivery",
    "FileCaptureBackend",
    "SlackDelivery",
    "advance_stage",
    "capture_photo",
    "deliver_report",
    "get_property_brief",
    "list_checklist_items",
    "list_open_work_orders",
    "make_delivery_adapter",
    "open_work_order",
    "record_checklist_result",
    "set_capture_backend",
    "set_delivery_adapter",
]
