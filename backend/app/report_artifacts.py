"""Tenant-scoped report artifacts and delivery lifecycle interfaces."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.evidence_storage import _safe


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class ReportArtifact:
    report_id: str
    path: Path


class ReportArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def create(self, *, org_id: str, home_id: str, inspection_id: str, html: str) -> ReportArtifact:
        report_id = str(uuid.uuid4())
        path = (
            self.root
            / _safe(org_id, "org_id")
            / _safe(home_id, "home_id")
            / "reports"
            / _safe(inspection_id, "inspection_id")
            / f"{report_id}.html"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return ReportArtifact(report_id, path)


class DeliveryAdapter(Protocol):
    async def deliver(self, artifact: ReportArtifact, destination: str) -> str: ...
