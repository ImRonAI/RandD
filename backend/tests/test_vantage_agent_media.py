import asyncio
import base64
import hashlib
import threading
import time
from pathlib import Path

import pytest

from app.approval_registry import ApprovalRegistry, ApprovalResolution
from app.evidence_storage import (
    EvidenceContext, EvidenceValidationError, LocalEvidenceStorage, S3EvidenceStorage,
    verify_original,
)
from app.escapia_read import ReadOnlyEscapiaAdapter
from app.memory_namespace import memory_namespace
from app.report_artifacts import ReportArtifactStore
from app.session_media import SessionMediaRegistry
from strands import tool


def test_session_media_isolates_frames_and_clips():
    registry = SessionMediaRegistry(max_frames=2)
    registry.add_frame("session-a", base64.b64encode(b"a").decode())
    registry.add_frame("session-b", base64.b64encode(b"b").decode())
    registry.arm_clip("session-a")
    registry.arm_clip("session-b")
    registry.deliver_clip("session-b", {"path": "b.webm"})

    assert registry.latest_frame("session-a").jpeg == b"a"
    assert registry.latest_frame("session-b").jpeg == b"b"
    assert registry.wait_for_clip("session-a", 0.01) is None
    assert registry.wait_for_clip("session-b", 0.01) == {"path": "b.webm"}


def test_session_media_isolates_multiple_yolo_detections():
    registry = SessionMediaRegistry(max_frames=2)
    payload = {
        "type": "yolo_detections",
        "timestamp": 123.0,
        "detections": [
            {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.8, "confidence": 0.91, "classId": 0, "label": "person"},
            {"x1": 0.5, "y1": 0.3, "x2": 0.9, "y2": 0.7, "confidence": 0.82, "classId": 56, "label": "chair"},
        ],
    }

    registry.publish_detections("session-a", payload, {"person": 1, "chair": 1})

    sequence, delivered = registry.wait_for_detections("session-a", 0, 0.01)
    assert sequence == 1
    assert delivered == payload
    assert registry.wait_for_detections("session-b", 0, 0.01) is None
    assert registry.detection_status("session-a") == {
        "active": False,
        "totals": {"chair": 1, "person": 1},
        "recent": [{"ts": 123.0, "objects": {"chair": 1, "person": 1}}],
    }


def test_browser_camera_compatible_wrappers_use_bound_session():
    from app import browser_camera

    first = browser_camera.bind_session("wrapper-a")
    browser_camera.add_frame(base64.b64encode(b"a").decode())
    browser_camera.unbind_session(first)
    second = browser_camera.bind_session("wrapper-b")
    browser_camera.add_frame(base64.b64encode(b"b").decode())
    assert browser_camera.latest_frame().jpeg == b"b"
    browser_camera.unbind_session(second)
    with pytest.raises(RuntimeError, match="camera_session_unbound"):
        browser_camera.latest_frame()
    first = browser_camera.bind_session("wrapper-a")
    assert browser_camera.latest_frame().jpeg == b"a"
    browser_camera.unbind_session(first)


def test_browser_camera_rejects_unbound_access():
    from app import browser_camera

    with pytest.raises(RuntimeError, match="camera_session_unbound"):
        browser_camera.add_frame(base64.b64encode(b"foreign").decode())


def test_yolo_waits_for_the_browser_camera_first_frame():
    from app import browser_camera, vision_tools
    import cv2
    import numpy as np

    session_id = "delayed-camera-frame"
    token = browser_camera.bind_session(session_id)
    encoded, jpeg = cv2.imencode(".jpg", np.zeros((640, 640, 3), dtype=np.uint8))
    assert encoded

    def deliver_frame() -> None:
        time.sleep(0.05)
        thread_token = browser_camera.bind_session(session_id)
        try:
            browser_camera.add_frame(base64.b64encode(jpeg.tobytes()).decode())
        finally:
            browser_camera.unbind_session(thread_token)

    delivery = threading.Thread(target=deliver_frame)
    delivery.start()
    try:
        result = vision_tools.yolo_vision.__wrapped__(action="detect")
    finally:
        delivery.join()
        browser_camera.discard_session(session_id)
        browser_camera.unbind_session(token)

    assert result["status"] == "success"
    assert result["content"] == [{"text": "👁 No objects detected in the current view."}]


def test_yolo_serializes_multiple_official_ultralytics_boxes():
    import numpy as np
    from ultralytics.engine.results import Results
    from app import vision_tools

    result = Results(
        orig_img=np.zeros((200, 400, 3), dtype=np.uint8),
        path="multi-detection.jpg",
        names={0: "person", 56: "chair"},
        boxes=np.array(
            [
                [40.0, 20.0, 200.0, 180.0, 0.91, 0.0],
                [220.0, 60.0, 360.0, 160.0, 0.82, 56.0],
            ],
            dtype=np.float32,
        ),
    )

    serialized = vision_tools._serialize_result(result)

    assert serialized["width"] == 400
    assert serialized["height"] == 200
    assert serialized["objects"] == {"chair": 1, "person": 1}
    assert len(serialized["detections"]) == 2
    assert serialized["detections"][0] == {
        "x1": pytest.approx(0.1),
        "y1": pytest.approx(0.1),
        "x2": pytest.approx(0.5),
        "y2": pytest.approx(0.9),
        "confidence": pytest.approx(0.91),
        "classId": 0,
        "label": "person",
    }
    assert serialized["detections"][1]["label"] == "chair"


def test_yolo_continuous_monitor_keeps_authenticated_camera_session():
    import cv2
    import numpy as np
    from app import browser_camera, vision_tools

    session_id = "continuous-yolo-session"
    token = browser_camera.bind_session(session_id)
    encoded, jpeg = cv2.imencode(".jpg", np.zeros((640, 640, 3), dtype=np.uint8))
    assert encoded
    browser_camera.add_frame(base64.b64encode(jpeg.tobytes()).decode())

    try:
        started = vision_tools.yolo_vision.__wrapped__(action="start", interval=0.5)
        event = browser_camera.wait_for_detections(0, timeout=5.0)
        stopped = vision_tools.yolo_vision.__wrapped__(action="stop")
    finally:
        browser_camera.discard_session(session_id)
        browser_camera.unbind_session(token)

    assert started["status"] == "success"
    assert event is not None
    assert event[1]["type"] == "yolo_detections"
    assert event[1]["width"] == 640
    assert event[1]["height"] == 640
    assert event[1]["detections"] == []
    assert stopped["status"] == "success"


def test_yolo_runtime_dependency_is_declared():
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"

    assert any(
        line.strip().lower().startswith("ultralytics")
        for line in requirements.read_text().splitlines()
    )


@pytest.mark.asyncio
async def test_approval_resolution_is_correlated_to_session_and_approval():
    registry = ApprovalRegistry()
    request = registry.request(
        session_id="session-a",
        inspection_id="inspection-1",
        rationale="Photo is sharp",
        media_id="media-1",
        timeout_seconds=1,
    )
    with pytest.raises(PermissionError):
        registry.resolve(
            session_id="session-b",
            resolution=ApprovalResolution(request.approval_id, "approve"),
        )
    registry.resolve(
        session_id="session-a",
        resolution=ApprovalResolution(request.approval_id, "reshoot", "too dark"),
    )
    resolved = await registry.wait(session_id="session-a", approval_id=request.approval_id)
    assert resolved.decision == "reshoot"
    assert resolved.feedback == "too dark"


@pytest.mark.asyncio
async def test_approval_expiry_emits_expired_event():
    events = []
    registry = ApprovalRegistry(event_sink=events.append)
    request = registry.request(
        session_id="s", inspection_id="i", rationale="r", media_id="m", timeout_seconds=0.01
    )
    with pytest.raises(asyncio.TimeoutError):
        await registry.wait(session_id="s", approval_id=request.approval_id)
    assert events[-1]["type"] == "approval_expired"


@pytest.mark.asyncio
async def test_expired_approval_cannot_be_resolved():
    registry = ApprovalRegistry()
    request = registry.request(
        session_id="s", inspection_id="i", rationale="r", media_id="m", timeout_seconds=0.001
    )
    await asyncio.sleep(0.005)
    with pytest.raises(TimeoutError, match="approval_expired"):
        registry.resolve(session_id="s", resolution=ApprovalResolution(request.approval_id, "approve"))


@pytest.mark.asyncio
async def test_approve_associates_atomically_and_emits_record_ids():
    events = []
    conversations = []
    calls = []

    async def associate(request, resolution):
        calls.append((request, resolution))
        return {"mediaAssociationId": "assoc-1", "resultId": "result-1"}

    registry = ApprovalRegistry(
        event_sink=events.append, conversation_sink=conversations.append,
        associate_approval=associate,
    )
    request = registry.request(
        session_id="s", inspection_id="i", item_id="item-1", result_id="result-1",
        asset_id="asset-1",
        proposed_verdict="PASS", rationale="sharp", media_id="m",
    )
    assert events[-1]["itemId"] == "item-1"
    assert events[-1]["resultId"] == "result-1"
    assert events[-1]["assetId"] == "asset-1"
    assert events[-1]["proposedVerdict"] == "PASS"
    registry.resolve(session_id="s", resolution=ApprovalResolution(request.approval_id, "approve"))
    await registry.wait(session_id="s", approval_id=request.approval_id)
    assert calls[0][0] == request
    assert events[-1]["recordIds"]["resultId"] == "result-1"
    assert conversations[-1]["type"] == "approval_message"


@pytest.mark.asyncio
async def test_reshoot_feedback_is_next_capture_instruction():
    events = []
    registry = ApprovalRegistry(event_sink=events.append)
    request = registry.request(session_id="s", inspection_id="i", rationale="r", media_id="m")
    registry.resolve(session_id="s", resolution=ApprovalResolution(
        request.approval_id, "reshoot", "Move closer to the data plate", "voice"
    ))
    await registry.wait(session_id="s", approval_id=request.approval_id)
    assert events[-1]["nextCaptureInstruction"] == "Move closer to the data plate"


def test_local_original_preserves_hash_and_separates_derivative(tmp_path):
    storage = LocalEvidenceStorage(tmp_path)
    context = EvidenceContext("org-1", "home-1", "inspection-1", "asset-1", "user-1")
    original = storage.put_original(context, "photo.jpg", b"original bytes", "image/jpeg")
    derivative = storage.put_derivative(original, "thumbnail", b"smaller", "image/jpeg")

    assert original.sha256 == hashlib.sha256(b"original bytes").hexdigest()
    assert storage.read(original) == b"original bytes"
    assert original.object_key.startswith("org-1/home-1/originals/")
    assert derivative.object_key.startswith("org-1/home-1/derivatives/")
    assert derivative.original_id == original.media_id


def test_reports_get_unique_tenant_scoped_artifact_paths(tmp_path):
    store = ReportArtifactStore(tmp_path)
    first = store.create(org_id="org-1", home_id="home-1", inspection_id="inspection-1", html="a")
    second = store.create(org_id="org-1", home_id="home-1", inspection_id="inspection-1", html="b")
    assert first.path != second.path
    assert "org-1/home-1/reports/inspection-1" in str(first.path)
    assert first.path.read_text() == "a"


def test_storage_rejects_unsafe_tenant_path(tmp_path):
    storage = LocalEvidenceStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.put_original(
            EvidenceContext("../other", "home", "inspection", "asset", "user"),
            "photo.jpg",
            b"x",
            "image/jpeg",
        )


def test_s3_adapter_fails_honestly_without_object_lock_config():
    with pytest.raises(RuntimeError, match="Object Lock"):
        S3EvidenceStorage(bucket="", client=object())


def test_original_verification_checks_mime_size_and_hash():
    data = b"photo bytes"
    size, digest = verify_original(
        data=data, mime_type="image/jpeg", expected_size=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest(),
    )
    assert size == len(data)
    assert digest == hashlib.sha256(data).hexdigest()
    with pytest.raises(EvidenceValidationError) as exc:
        verify_original(data=data, mime_type="text/plain")
    assert exc.value.code == "unsupported_media_type"
    with pytest.raises(EvidenceValidationError) as exc:
        verify_original(data=data, mime_type="image/jpeg", expected_sha256="0" * 64)
    assert exc.value.code == "media_hash_mismatch"
    assert exc.value.retryable is True


def test_memory_namespace_is_tenant_safe():
    assert memory_namespace("org-1", "portfolio-1", "home-1") == "orgs/org-1/portfolios/portfolio-1/homes/home-1"
    with pytest.raises(ValueError):
        memory_namespace("org-1", "portfolio-1", "../home-2")


def test_agent_uses_six_core_and_session_tools(monkeypatch):
    import app.agent as agent_module

    captured = {}

    class FakeBidiAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    @tool
    def session_inventory_tool() -> str:
        """A tenant-bound tool supplied by the live session."""
        return "ok"

    monkeypatch.setattr(agent_module, "BidiAgent", FakeBidiAgent)
    monkeypatch.setattr(agent_module, "build_model", lambda *args: object())
    monkeypatch.setattr(agent_module, "memory_tools", lambda: [])

    agent_module.create_agent(
        mode="audio",
        voice="Puck",
        provider="gemini",
        session_tools=[session_inventory_tool],
    )

    names = {
        getattr(item, "tool_name", "")
        or getattr(item, "__name__", "").rsplit(".", 1)[-1]
        for item in captured["tools"]
    }
    assert names == {
        "shell",
        "editor",
        "load_tool",
        "mcp_client",
        "http_request",
        "environment",
        "session_inventory_tool",
    }
    assert captured.get("load_tools_from_directory", False) is False
    assert "Use all available tools implicitly" not in captured["system_prompt"]
    assert "Never scan the filesystem root" in captured["system_prompt"]
    assert "call load_tool at most once for each missing tool" in captured["system_prompt"]
    assert "retry a successful load" in captured["system_prompt"]
    assert str(Path(agent_module.__file__).resolve().parent) in captured["system_prompt"]


class FakeEscapiaClient:
    def __init__(self):
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"results": []}


@pytest.mark.asyncio
async def test_escapia_adapter_exposes_reads_and_rejects_writes():
    client = FakeEscapiaClient()
    adapter = ReadOnlyEscapiaAdapter(client)
    await adapter.search_units(page_number=1)
    assert client.calls[0][0] == "GET"
    with pytest.raises(PermissionError, match="read-only"):
        await adapter.request("POST", "/hsapi/SaveWorkOrder", json={})
