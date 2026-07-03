"""Shared fixtures: tmp migrated+seeded DB, run context, fake backends."""

from __future__ import annotations

from pathlib import Path

import pytest
from strqc_db.migrate import migrate
from strqc_db.seed import seed

from strqc_agent.context import AgentRunContext, clear_context, set_context
from strqc_agent.tools.camera import set_capture_backend
from strqc_agent.tools.slack_delivery import DryRunDelivery, set_delivery_adapter


class FakeCaptureBackend:
    """Deterministic capture backend: writes known bytes, records calls."""

    def __init__(self, photo_dir: Path) -> None:
        self.photo_dir = photo_dir
        self.calls: list[dict] = []

    def capture(self, *, caption: str, purpose: str) -> Path:
        self.calls.append({"caption": caption, "purpose": purpose})
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        path = self.photo_dir / f"fake_{len(self.calls)}.jpg"
        path.write_bytes(b"fake-image-bytes")
        return path


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test.sqlite")
    migrate(path)
    seed(path)
    return path


@pytest.fixture
def ctx(db_path: str, tmp_path: Path):
    context = AgentRunContext(
        db_path=db_path,
        photo_dir=str(tmp_path / "photos"),
        task_id=1,
        property_id=1,
        checklist_template_id=1,
        stakeholder_id=5,  # Dana, QC inspector
    )
    set_context(context)
    yield context
    clear_context()
    set_capture_backend(None)
    set_delivery_adapter(None)


@pytest.fixture
def fake_camera(ctx, tmp_path: Path) -> FakeCaptureBackend:
    backend = FakeCaptureBackend(tmp_path / "photos")
    set_capture_backend(backend)
    return backend


@pytest.fixture
def dry_run_delivery(ctx) -> DryRunDelivery:
    adapter = DryRunDelivery()
    set_delivery_adapter(adapter)
    return adapter
