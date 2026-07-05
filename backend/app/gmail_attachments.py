"""Gmail send/reply with file attachments (strands_google's gmail_send cannot).

Builds a multipart MIME message (HTML/PDF/DOC and any other file type via
mimetype guess) and sends it through the same ``use_google`` gateway the other
Gmail tools use, so authentication is identical (user OAuth token).
"""

import base64
import json
import mimetypes
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool

# Gmail rejects messages over 25 MB encoded.
_MAX_TOTAL_BYTES = 25 * 1024 * 1024


def _resolve(path: str) -> Path:
    """Resolve an attachment path: absolute, cwd (workspace), or repo-known dirs."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    workspace = Path(__file__).resolve().parent.parent / "workspace"
    for base in (Path.cwd(), workspace, workspace / "reports", workspace / "captures"):
        if (base / candidate).exists():
            return base / candidate
    return candidate


def _use_google(**kwargs: Any) -> Dict[str, Any]:
    from strands_google.use_google import use_google

    return use_google(credential_type="oauth", **kwargs)


def _json_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        text = result["content"][0]["text"]
        return json.loads(text.split("Response:\n", 1)[1])
    except Exception:
        return None


@tool
def gmail_send_with_attachments(
    to: str,
    subject: str,
    body: str,
    attachments: List[str],
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    html: bool = False,
    reply_to_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send (or reply to) a Gmail email with file attachments.

    Use this instead of gmail_send whenever files must be attached — inspection
    report HTML exports, PDFs, Word documents, photos, or video clips. Paths
    are resolved against the agent workspace (e.g. "reports/inspection-report-latest.html").

    Args:
        to: Recipient email address (comma-separate multiple).
        subject: Email subject. For replies, pass the original subject; "Re:"
            is added automatically when missing.
        body: Message body (plain text, or HTML when html=True).
        attachments: File paths to attach. Workspace-relative or absolute.
        cc: Optional list of CC addresses.
        bcc: Optional list of BCC addresses.
        html: Treat body as HTML.
        reply_to_message_id: Gmail message id to reply to — threads the mail
            and sets In-Reply-To/References automatically.

    Returns:
        Dict with status and content (sent message id / thread id).
    """
    try:
        message = EmailMessage()
        message["To"] = to
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)

        thread_id: Optional[str] = None
        if reply_to_message_id:
            original = _use_google(
                service="gmail", version="v1", resource="users.messages", method="get",
                parameters={"userId": "me", "id": reply_to_message_id, "format": "metadata",
                            "metadataHeaders": ["Message-ID", "Subject"]},
                label="Fetch original message for reply headers",
            )
            payload = _json_payload(original) or {}
            thread_id = payload.get("threadId")
            headers = {h["name"].lower(): h["value"]
                       for h in (payload.get("payload", {}) or {}).get("headers", [])}
            if headers.get("message-id"):
                message["In-Reply-To"] = headers["message-id"]
                message["References"] = headers["message-id"]
            if not subject and headers.get("subject"):
                subject = headers["subject"]
            if subject and not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
        message["Subject"] = subject

        if html:
            message.set_content("This message contains HTML content.")
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        total = 0
        attached = []
        for raw_path in attachments:
            path = _resolve(raw_path)
            if not path.exists():
                return {"status": "error",
                        "content": [{"text": f"❌ Attachment not found: {raw_path}"}]}
            data = path.read_bytes()
            total += len(data)
            if total > _MAX_TOTAL_BYTES:
                return {"status": "error",
                        "content": [{"text": f"❌ Attachments exceed Gmail's 25 MB limit "
                                             f"({total // (1024*1024)} MB so far)."}]}
            mime, _ = mimetypes.guess_type(path.name)
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            message.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
            attached.append(f"{path.name} ({len(data)} bytes, {mime or 'application/octet-stream'})")

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body: Dict[str, Any] = {"raw": raw}
        if thread_id:
            send_body["threadId"] = thread_id

        result = _use_google(
            service="gmail", version="v1", resource="users.messages", method="send",
            parameters={"userId": "me", "body": send_body},
            label=f"Send email with {len(attached)} attachment(s)",
        )
        if result.get("status") != "success":
            return result
        sent = _json_payload(result) or {}
        return {"status": "success",
                "content": [{"text": f"📧 Sent to {to} (message id {sent.get('id', '?')}, "
                                     f"thread {sent.get('threadId', '?')}).\nAttached: "
                                     + "; ".join(attached)}]}
    except Exception as exc:
        return {"status": "error", "content": [{"text": f"❌ Send failed: {exc}"}]}
