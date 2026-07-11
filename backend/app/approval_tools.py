"""Session-bound agent tool for the in-frame photo approval protocol."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from strands import tool

from app.approval_registry import ApprovalRegistry

_registry: ContextVar[ApprovalRegistry | None] = ContextVar("vantage_approval_registry", default=None)
_session: ContextVar[str | None] = ContextVar("vantage_approval_session", default=None)


@contextmanager
def approval_scope(session_id: str, registry: ApprovalRegistry) -> Iterator[None]:
    registry_token = _registry.set(registry)
    session_token = _session.set(session_id)
    try:
        yield
    finally:
        _session.reset(session_token)
        _registry.reset(registry_token)


@tool
async def request_photo_approval(
    inspection_id: str,
    media_id: str,
    rationale: str,
    item_id: str = "",
    asset_id: str = "",
    proposed_verdict: str = "",
) -> dict:
    """Show a captured original inside the persistent agent UI and wait for human approval.

    Use only after the original upload has persisted. Supply the exact checklist
    item or asset destination. The inspector can approve, cancel, or request a
    retake with a voice/text instruction; never infer approval from conversation.
    """
    registry, session_id = _registry.get(), _session.get()
    if registry is None or not session_id:
        return {"status": "error", "code": "approval_session_unbound", "retryable": True}
    request = registry.request(
        session_id=session_id, inspection_id=inspection_id, media_id=media_id,
        rationale=rationale, item_id=item_id or None, asset_id=asset_id or None,
        proposed_verdict=proposed_verdict or None, timeout_seconds=300,
    )
    try:
        resolution = await registry.wait(session_id=session_id, approval_id=request.approval_id)
    except TimeoutError:
        return {"status": "error", "code": "approval_expired", "retryable": True,
                "approvalId": request.approval_id}
    return {"status": "success", "approvalId": request.approval_id,
            "decision": resolution.decision, "feedback": resolution.feedback,
            "inputMode": resolution.input_mode}
