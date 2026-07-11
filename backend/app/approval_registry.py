"""Persistent, correlated human approvals for authenticated field sessions."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    session_id: str
    inspection_id: str
    rationale: str
    media_id: str
    expires_at: float
    item_id: str | None = None
    asset_id: str | None = None
    proposed_verdict: str | None = None


@dataclass(frozen=True)
class ApprovalResolution:
    approval_id: str
    decision: str
    feedback: str | None = None
    input_mode: str | None = None


class ApprovalStore(Protocol):
    """Persistence adapter. A database implementation can survive reconnects."""

    def put(self, request: ApprovalRequest) -> None: ...
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def delete(self, approval_id: str) -> None: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self.records: dict[str, ApprovalRequest] = {}

    def put(self, request: ApprovalRequest) -> None:
        self.records[request.approval_id] = request

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self.records.get(approval_id)

    def delete(self, approval_id: str) -> None:
        self.records.pop(approval_id, None)


@dataclass
class _Pending:
    request: ApprovalRequest
    future: asyncio.Future[ApprovalResolution]


AssociationCallback = Callable[[ApprovalRequest, ApprovalResolution], dict[str, Any] | Awaitable[dict[str, Any]]]


class ApprovalRegistry:
    def __init__(self, event_sink: Callable[[dict], None] | None = None, *,
                 store: ApprovalStore | None = None,
                 associate_approval: AssociationCallback | None = None,
                 conversation_sink: Callable[[dict], None] | None = None) -> None:
        self._pending: dict[str, _Pending] = {}
        self._event_sink = event_sink or (lambda event: None)
        self._conversation_sink = conversation_sink or (lambda event: None)
        self._store = store or InMemoryApprovalStore()
        self._associate_approval = associate_approval

    def request(self, *, session_id: str, inspection_id: str, rationale: str,
                media_id: str, item_id: str | None = None, asset_id: str | None = None,
                proposed_verdict: str | None = None,
                timeout_seconds: float = 120) -> ApprovalRequest:
        if not all((session_id, inspection_id, media_id)):
            raise ValueError("session_id, inspection_id, and media_id are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        request = ApprovalRequest(
            str(uuid.uuid4()), session_id, inspection_id, rationale, media_id,
            time.time() + timeout_seconds, item_id, asset_id, proposed_verdict,
        )
        self._store.put(request)
        self._pending[request.approval_id] = _Pending(
            request, asyncio.get_running_loop().create_future()
        )
        self._event_sink({
            "type": "approval_requested", "approvalId": request.approval_id,
            "inspectionId": inspection_id, "itemId": item_id, "assetId": asset_id,
            "destinationLabel": item_id or asset_id or "Unresolved destination",
            "proposedVerdict": proposed_verdict, "rationale": rationale,
            "mediaId": media_id, "expiresAt": request.expires_at,
        })
        return request

    def _lookup(self, approval_id: str) -> _Pending:
        pending = self._pending.get(approval_id)
        persisted = self._store.get(approval_id)
        if pending is None or persisted is None:
            raise KeyError("approval_not_found")
        if time.time() >= pending.request.expires_at:
            self._expire(approval_id)
            raise TimeoutError("approval_expired")
        return pending

    def _expire(self, approval_id: str) -> None:
        pending = self._pending.pop(approval_id, None)
        self._store.delete(approval_id)
        if pending and not pending.future.done():
            pending.future.cancel()
        self._event_sink({"type": "approval_expired", "approvalId": approval_id})

    def resolve(self, *, session_id: str, resolution: ApprovalResolution) -> None:
        pending = self._lookup(resolution.approval_id)
        if pending.request.session_id != session_id:
            raise PermissionError("approval belongs to another session")
        if resolution.decision not in {"approve", "reshoot", "cancel"}:
            raise ValueError("invalid approval decision")
        if resolution.decision == "reshoot" and not (resolution.feedback or "").strip():
            raise ValueError("reshoot feedback is required")
        if resolution.input_mode not in {None, "text", "voice"}:
            raise ValueError("invalid input mode")
        if not pending.future.done():
            pending.future.set_result(resolution)

    async def wait(self, *, session_id: str, approval_id: str) -> ApprovalResolution:
        pending = self._lookup(approval_id)
        if pending.request.session_id != session_id:
            raise PermissionError("approval belongs to another session")
        try:
            result = await asyncio.wait_for(
                asyncio.shield(pending.future), pending.request.expires_at - time.time()
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if self._store.get(approval_id) is not None:
                self._expire(approval_id)
            raise asyncio.TimeoutError

        event: dict[str, Any]
        if result.decision == "approve":
            if self._associate_approval is None:
                raise RuntimeError("approval association repository is not configured")
            records = self._associate_approval(pending.request, result)
            if inspect.isawaitable(records):
                records = await records
            event = {"type": "approval_completed", "approvalId": approval_id,
                     "decision": "approve", "recordIds": records}
            self._conversation_sink({"type": "approval_message", "approvalId": approval_id,
                                     "message": "Photo approved and attached.", "recordIds": records})
        elif result.decision == "reshoot":
            event = {"type": "approval_completed", "approvalId": approval_id,
                     "decision": "reshoot", "nextCaptureInstruction": result.feedback,
                     "inputMode": result.input_mode}
            self._conversation_sink({"type": "capture_instruction", "approvalId": approval_id,
                                     "instruction": result.feedback, "inputMode": result.input_mode})
        else:
            event = {"type": "approval_cancelled", "approvalId": approval_id, "decision": "cancel"}
        self._event_sink(event)
        self._pending.pop(approval_id, None)
        self._store.delete(approval_id)
        return result

    def restore(self, request: ApprovalRequest) -> None:
        """Rehydrate a persisted request after reconnect/server restart."""
        if request.expires_at <= time.time():
            self._store.delete(request.approval_id)
            return
        self._store.put(request)
        self._pending[request.approval_id] = _Pending(
            request, asyncio.get_running_loop().create_future()
        )
