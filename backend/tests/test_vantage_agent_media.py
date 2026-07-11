import asyncio
import base64
import hashlib

import pytest

from app.approval_registry import ApprovalRegistry, ApprovalResolution
from app.evidence_storage import (
    EvidenceContext, EvidenceValidationError, LocalEvidenceStorage, S3EvidenceStorage,
    verify_original,
)
from app.escapia_read import ReadOnlyEscapiaAdapter
from app.inventory_tools import AgentInventoryService, ToolContext
from app.memory_namespace import memory_namespace
from app.report_artifacts import ReportArtifactStore
from app.session_media import SessionMediaRegistry
from app.tool_policy import FIELD_TOOL_ALLOWLIST, validate_field_tools


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
        session_id="s", inspection_id="i", item_id="item-1", asset_id="asset-1",
        proposed_verdict="PASS", rationale="sharp", media_id="m",
    )
    assert events[-1]["itemId"] == "item-1"
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


class RecordingRepository:
    def __init__(self):
        self.calls = []

    async def create_room(self, context, payload, idempotency_key):
        self.calls.append((context, payload, idempotency_key))
        return {"id": payload["client_id"], "name": payload["name"]}


@pytest.mark.asyncio
async def test_inventory_tool_passes_structured_authorization_context():
    repo = RecordingRepository()
    service = AgentInventoryService(repo)
    context = ToolContext("org-1", "user-1", frozenset({"inspector"}), "home-1", "inspection-1", "s-1")
    result = await service.create_room(
        context,
        {"client_id": "room-client-1", "room_type_id": "bedroom", "name": "Bedroom 2"},
        "idem-1",
    )
    assert result == {"ok": True, "data": {"id": "room-client-1", "name": "Bedroom 2"}}
    assert repo.calls[0][0] is context


@pytest.mark.asyncio
async def test_inventory_tool_returns_structured_authorization_error():
    service = AgentInventoryService(RecordingRepository())
    context = ToolContext("", "user-1", frozenset(), "home-1", "inspection-1", "s-1")
    result = await service.list_rooms(context)
    assert result["ok"] is False
    assert result["error"]["code"] == "authorization_context_missing"


@pytest.mark.asyncio
async def test_all_mutating_inventory_tools_require_stable_ids():
    service = AgentInventoryService(RecordingRepository())
    context = ToolContext("org", "user", frozenset({"inspector"}), "home", "inspection", "session")
    for operation in (
        "update_room", "archive_room", "create_asset", "update_asset", "move_asset",
        "attach_original_photo", "record_research_result", "mark_low_confidence_value",
        "save_walkthrough_progress", "complete_onboarding_assessment",
    ):
        result = await service.invoke(operation, context, name="x")
        assert result["error"]["code"] == "idempotency_required"


def test_memory_namespace_is_tenant_safe():
    assert memory_namespace("org-1", "portfolio-1", "home-1") == "orgs/org-1/portfolios/portfolio-1/homes/home-1"
    with pytest.raises(ValueError):
        memory_namespace("org-1", "portfolio-1", "../home-2")


def test_field_allowlist_excludes_runtime_tools():
    validate_field_tools(FIELD_TOOL_ALLOWLIST)
    for forbidden in ("shell", "editor", "environment", "http_request", "load_tool"):
        assert forbidden not in FIELD_TOOL_ALLOWLIST
    with pytest.raises(ValueError):
        validate_field_tools(["create_room", "shell"])


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
