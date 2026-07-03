"""Camera tool — structured photo capture persisted to ``photo_memory``.

AGENTS.md §4, TASKS.md M3.1. There is no physical camera in this milestone:
capture goes through a pluggable :class:`CaptureBackend`. The default
:class:`FileCaptureBackend` writes a placeholder file under the context's
``photo_dir``; the real device camera arrives with the frontend (M7).
The tool contract (params, DB row, hash, include_in_report) is what matters.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from strands import tool
from strqc_db import repositories

from ..context import get_context


class CaptureBackend(Protocol):
    """Produces an image file for a capture request; returns its path."""

    def capture(self, *, caption: str, purpose: str) -> Path:
        """Capture (or fetch) an image and return the local file path."""
        ...


class FileCaptureBackend:
    """Placeholder backend: creates a stub image file under ``photo_dir``."""

    def __init__(self, photo_dir: str | Path) -> None:
        self.photo_dir = Path(photo_dir)

    def capture(self, *, caption: str, purpose: str) -> Path:
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
        path = self.photo_dir / name
        path.write_bytes(
            f"PLACEHOLDER PHOTO\npurpose={purpose}\ncaption={caption}\n".encode()
        )
        return path


_backend: CaptureBackend | None = None


def set_capture_backend(backend: CaptureBackend | None) -> None:
    """Install the capture backend (assembler / tests)."""
    global _backend
    _backend = backend


def _get_backend() -> CaptureBackend:
    if _backend is not None:
        return _backend
    return FileCaptureBackend(get_context().photo_dir)


@tool
def capture_photo(caption: str, purpose: str = "checklist", include_in_report: bool = False) -> dict:
    """Capture a photo of the current area and store it as evidence.

    Args:
        caption: What the photo shows, tied to the checklist item or issue.
        purpose: Why it was taken (e.g. checklist, damage, maintenance_before, owner_report).
        include_in_report: Whether this photo should be embedded in the readiness report.

    Returns:
        The stored photo id and file uri.
    """
    ctx = get_context()
    path = _get_backend().capture(caption=caption, purpose=purpose)
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = {"purpose": purpose, "captured_at": datetime.now(UTC).isoformat()}
    conn = ctx.get_conn()
    try:
        photo_id = repositories.add_photo(
            conn,
            property_id=ctx.property_id,
            task_id=ctx.task_id,
            inspection_id=ctx.inspection_id,
            uri=str(path),
            caption=caption,
            content_hash=content_hash,
            include_in_report=include_in_report,
            metadata_json=json.dumps(metadata),
        )
    finally:
        conn.close()
    return {"photo_memory_id": photo_id, "uri": str(path), "content_hash": content_hash}
