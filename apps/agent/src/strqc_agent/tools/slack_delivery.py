"""Report delivery — swappable adapter, Slack-first (AGENTS.md Addendum 1).

V1 ships Slack as the only channel, via the ``files.uploadV2`` flow
(``files.getUploadURLExternal`` → upload bytes → ``files.completeUploadExternal``).
The HTTP layer is injectable and the default adapter is a no-network
:class:`DryRunDelivery` whenever ``SLACK_BOT_TOKEN`` is empty, so tests and dev
never touch the network. Email/Teams adapters arrive in Phase 2.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from strands import tool
from strqc_shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

# HTTP layer: (url, body bytes, headers) -> response body bytes.
HttpPost = Callable[[str, bytes, dict], bytes]


class DeliveryAdapter(Protocol):
    """Sends a finished report file plus a short summary to a stakeholder channel."""

    def send(self, report_path: str, summary: str) -> bool:
        """Deliver the report; return True on success."""
        ...


class DryRunDelivery:
    """No-network adapter: records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, report_path: str, summary: str) -> bool:
        self.sent.append((report_path, summary))
        logger.info("dry-run delivery: %s (%s)", report_path, summary)
        return True


def _urllib_post(url: str, body: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed https URLs
        return resp.read()


class SlackDelivery:
    """Slack Web API delivery via the external-upload (files.uploadV2) flow."""

    API_BASE = "https://slack.com/api"

    def __init__(self, bot_token: str, channel_id: str, http_post: HttpPost | None = None) -> None:
        if not bot_token:
            raise ValueError("SlackDelivery requires a bot token")
        self._token = bot_token
        self._channel_id = channel_id
        self._post = http_post or _urllib_post

    def _api(self, method: str, *, form: dict | None = None, payload: dict | None = None) -> dict:
        url = f"{self.API_BASE}/{method}"
        headers = {"Authorization": f"Bearer {self._token}"}
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            body = json.dumps(payload).encode()
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(form or {}).encode()
        return json.loads(self._post(url, body, headers))

    def send(self, report_path: str, summary: str) -> bool:
        path = Path(report_path)
        data = path.read_bytes()

        ticket = self._api(
            "files.getUploadURLExternal", form={"filename": path.name, "length": len(data)}
        )
        if not ticket.get("ok"):
            logger.error("slack getUploadURLExternal failed: %s", ticket.get("error"))
            return False

        self._post(ticket["upload_url"], data, {"Content-Type": "application/octet-stream"})

        complete = self._api(
            "files.completeUploadExternal",
            payload={
                "files": [{"id": ticket["file_id"], "title": path.name}],
                "channel_id": self._channel_id,
                "initial_comment": summary,
            },
        )
        if not complete.get("ok"):
            logger.error("slack completeUploadExternal failed: %s", complete.get("error"))
            return False
        return True


def make_delivery_adapter(settings: Settings | None = None, http_post: HttpPost | None = None) -> DeliveryAdapter:
    """Slack when a bot token is configured; otherwise a dry run (no network)."""
    settings = settings or get_settings()
    if settings.slack_bot_token:
        return SlackDelivery(settings.slack_bot_token, settings.slack_default_channel_id, http_post)
    return DryRunDelivery()


_adapter: DeliveryAdapter | None = None


def set_delivery_adapter(adapter: DeliveryAdapter | None) -> None:
    """Install the delivery adapter (assembler / tests)."""
    global _adapter
    _adapter = adapter


def _get_adapter() -> DeliveryAdapter:
    global _adapter
    if _adapter is None:
        _adapter = make_delivery_adapter()
    return _adapter


@tool
def deliver_report(report_path: str, summary: str = "") -> dict:
    """Send a signed-off readiness report to the stakeholder channel (Slack in v1).

    Args:
        report_path: Local file path of the assembled report to attach.
        summary: One-line notice to accompany the attachment.

    Returns:
        Delivery status (SENT or FAILED) and channel kind.
    """
    adapter = _get_adapter()
    ok = adapter.send(report_path, summary)
    return {
        "delivery_status": "SENT" if ok else "FAILED",
        "adapter": type(adapter).__name__,
    }
