"""Report delivery adapters — no network anywhere."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

from strqc_shared.config import Settings

from strqc_agent.tools.slack_delivery import (
    DryRunDelivery,
    SlackDelivery,
    deliver_report,
    make_delivery_adapter,
)


class FakeHttp:
    """Records posts; scripted Slack API responses."""

    def __init__(self, *, ticket_ok: bool = True, complete_ok: bool = True) -> None:
        self.calls: list[tuple[str, bytes, dict]] = []
        self._ticket_ok = ticket_ok
        self._complete_ok = complete_ok

    def __call__(self, url: str, body: bytes, headers: dict) -> bytes:
        self.calls.append((url, body, headers))
        if url.endswith("files.getUploadURLExternal"):
            return json.dumps(
                {"ok": self._ticket_ok, "upload_url": "https://files.slack.test/u/1", "file_id": "F123"}
            ).encode()
        if url.endswith("files.completeUploadExternal"):
            return json.dumps({"ok": self._complete_ok}).encode()
        return b"OK"  # raw upload endpoint


def test_slack_delivery_three_step_flow(tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-fake")
    http = FakeHttp()
    adapter = SlackDelivery("xoxb-test", "C123", http_post=http)

    assert adapter.send(str(report), "Unit BBL-014 — ready for guests") is True
    assert len(http.calls) == 3

    ticket_url, ticket_body, ticket_headers = http.calls[0]
    assert ticket_url.endswith("/files.getUploadURLExternal")
    assert ticket_headers["Authorization"] == "Bearer xoxb-test"
    form = parse_qs(ticket_body.decode())
    assert form["filename"] == ["report.pdf"]
    assert form["length"] == [str(len(b"%PDF-fake"))]

    upload_url, upload_body, _ = http.calls[1]
    assert upload_url == "https://files.slack.test/u/1"
    assert upload_body == b"%PDF-fake"

    complete_url, complete_body, _ = http.calls[2]
    assert complete_url.endswith("/files.completeUploadExternal")
    payload = json.loads(complete_body)
    assert payload["files"] == [{"id": "F123", "title": "report.pdf"}]
    assert payload["channel_id"] == "C123"
    assert payload["initial_comment"] == "Unit BBL-014 — ready for guests"


def test_slack_delivery_reports_failure(tmp_path):
    report = tmp_path / "r.pdf"
    report.write_bytes(b"x")
    adapter = SlackDelivery("xoxb-test", "C123", http_post=FakeHttp(ticket_ok=False))
    assert adapter.send(str(report), "s") is False


def test_factory_defaults_to_dry_run_without_token():
    settings = Settings(slack_bot_token="", _env_file=None)
    assert isinstance(make_delivery_adapter(settings), DryRunDelivery)

    settings = Settings(slack_bot_token="xoxb-x", slack_default_channel_id="C1", _env_file=None)
    assert isinstance(make_delivery_adapter(settings), SlackDelivery)


def test_deliver_report_tool_uses_installed_adapter(ctx, dry_run_delivery, tmp_path):
    report = tmp_path / "r.pdf"
    report.write_bytes(b"x")
    out = deliver_report(report_path=str(report), summary="ready")
    assert out["delivery_status"] == "SENT"
    assert dry_run_delivery.sent == [(str(report), "ready")]
