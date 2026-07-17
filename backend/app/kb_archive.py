"""Archive inspection reports into the Bedrock Knowledge Base's S3 bucket.

Every house gets its own folder tree in the bucket (``BEDROCK_KB_S3_BUCKET``):

- ``memories/<house>/inspections/<timestamp>-summary.txt`` — plain-text digest
  of each inspection (verdicts, notes, walkthroughs, repairs). Under the
  data-source prefix, so it becomes searchable memory (search_memory).
- ``memories/<house>/notes/<timestamp>-note.txt`` — additional site memories
  that do NOT come from inspections (quirks, access details, history), written
  by the ``save_site_memory`` tool. Also searchable.
- ``artifacts/<house>/inspections/<timestamp>-report.html`` — the full
  self-contained interactive form (media baked in). Deliberately outside the
  data-source prefix: it is the durable artifact, not vector-index fodder.

Best-effort ``StartIngestionJob`` follows uploads when ``BEDROCK_KB_ID`` +
``BEDROCK_KB_DATA_SOURCE_ID`` are configured.

Bootstrap a house's folders with: ``python -m app.kb_archive --init``
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from strands import tool

REPORTS_DIR = Path(__file__).resolve().parent.parent / "workspace" / "reports"
LATEST_REPORT = REPORTS_DIR / "inspection-report-latest.html"

_STATE_RE = re.compile(r"window\.__QC_STATE__ = (\{.*?\});</script>", re.S)


def _bucket() -> Optional[str]:
    return os.getenv("BEDROCK_KB_S3_BUCKET")


def _memories_base() -> str:
    return os.getenv("BEDROCK_KB_S3_PREFIX", "memories/").strip("/")


def _slug(name: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9-]+", "-", str(name or "")).strip("-").lower() or "unknown"


def _house_prefixes(house_slug: str) -> Dict[str, str]:
    """The per-house folder tree inside the KB bucket."""
    base = _memories_base()
    return {
        "inspections": f"{base}/{house_slug}/inspections",
        "notes": f"{base}/{house_slug}/notes",
        "artifacts": f"artifacts/{house_slug}/inspections",
    }


def _ensure_house_folders(s3: Any, bucket: str, house_slug: str) -> None:
    """Idempotently create the house's folder markers (visible in the console)."""
    for prefix in _house_prefixes(house_slug).values():
        s3.put_object(Bucket=bucket, Key=f"{prefix}/", Body=b"")


def _s3() -> Any:
    import boto3

    return boto3.client("s3")


def extract_state(html: str) -> Optional[Dict[str, Any]]:
    """Pull the embedded ``window.__QC_STATE__`` payload out of a report export."""
    m = _STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def summarize_state(state: Dict[str, Any]) -> str:
    """Render the inspection state as a plain-text knowledge document."""
    lines = [
        f"TURNOVER INSPECTION REPORT — {state.get('property', 'unknown property')}",
        f"Archived: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        f"Signed off: {'YES — ready for guests' if state.get('signedOff') else 'no'}",
        "",
    ]
    for sec in state.get("sections", []) or []:
        lines.append(f"SECTION: {sec.get('id', '?')}")
        note = (sec.get("note") or "").strip()
        if note:
            lines.append(f"  Walkthrough note: {note}")
        if sec.get("video"):
            lines.append("  Walkthrough video: attached")
        lines.append("")
    items = state.get("items", []) or []
    done = sum(1 for i in items if i.get("checked"))
    lines.append(f"LINE ITEMS ({done}/{len(items)} complete):")
    for item in items:
        mark = "PASS" if item.get("checked") else "OPEN"
        entry = f"  [{mark}] {item.get('label', item.get('id', '?'))}"
        photos = item.get("photos") or []
        if photos:
            entry += f" ({len(photos)} photo{'s' if len(photos) != 1 else ''})"
        lines.append(entry)
        note = (item.get("note") or "").strip()
        if note:
            lines.append(f"        note: {note}")
    repairs = (state.get("repairs") or "").strip()
    lines += ["", f"REPAIRS NEEDED: {repairs if repairs else 'none logged'}"]
    return "\n".join(lines)


def _start_ingestion(s3_client_unused: Any = None) -> Optional[str]:
    """Best-effort Bedrock KB ingestion so the new summary becomes searchable."""
    kb_id = os.getenv("BEDROCK_KB_ID")
    ds_id = os.getenv("BEDROCK_KB_DATA_SOURCE_ID")
    if not (kb_id and ds_id):
        return None
    try:
        import boto3

        client = boto3.client("bedrock-agent")
        response = client.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
        response_dict = response if isinstance(response, dict) else {}
        ingestion_job = response_dict.get("ingestionJob")
        if isinstance(ingestion_job, dict):
            ingestion_job_id = ingestion_job.get("ingestionJobId")
            if isinstance(ingestion_job_id, str):
                return ingestion_job_id
        return None
    except Exception:
        return None  # sync happens on the KB's own schedule instead


def archive_report(html: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Upload the report (summary + full artifact) into the KB bucket folder."""
    bucket = _bucket()
    if not bucket:
        raise RuntimeError(
            "BEDROCK_KB_S3_BUCKET is not set — configure the knowledge-base bucket "
            "in backend/.env to enable report archiving."
        )
    state = extract_state(html)
    slug = _slug((state or {}).get("property", "unknown"))
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    summary = summarize_state(state) if state else "Inspection report (no embedded state)."
    if note:
        summary = f"{summary}\n\nARCHIVE NOTE: {note}"

    prefixes = _house_prefixes(slug)
    summary_key = f"{prefixes['inspections']}/{stamp}-summary.txt"
    artifact_key = f"{prefixes['artifacts']}/{stamp}-report.html"

    s3 = _s3()
    _ensure_house_folders(s3, bucket, slug)
    s3.put_object(Bucket=bucket, Key=summary_key, Body=summary.encode("utf-8"),
                  ContentType="text/plain; charset=utf-8")
    s3.put_object(Bucket=bucket, Key=artifact_key, Body=html.encode("utf-8"),
                  ContentType="text/html; charset=utf-8")
    ingestion_job = _start_ingestion()

    from app.report_db import record_archive

    form_uuid = record_archive(
        state, len(html.encode("utf-8")),
        s3_summary_uri=f"s3://{bucket}/{summary_key}",
        s3_artifact_uri=f"s3://{bucket}/{artifact_key}",
    )

    return {
        "bucket": bucket,
        "summary_uri": f"s3://{bucket}/{summary_key}",
        "artifact_uri": f"s3://{bucket}/{artifact_key}",
        "ingestion_job_id": ingestion_job,
        "form_uuid": form_uuid,
        "signed_off": bool((state or {}).get("signedOff")),
    }


def ensure_folders(house: str = "unknown") -> Dict[str, str]:
    """Create a house's folder markers in the KB bucket (idempotent)."""
    bucket = _bucket()
    if not bucket:
        raise RuntimeError("BEDROCK_KB_S3_BUCKET is not set.")
    s3 = _s3()
    slug = _slug(house)
    _ensure_house_folders(s3, bucket, slug)
    return {"bucket": bucket, "folders": ", ".join(_house_prefixes(slug).values())}


@tool
def save_site_memory(property_name: str, note: str) -> Dict[str, Any]:
    """Save a site memory about a house that does NOT come from an inspection.

    Writes the note into the house's own folder in the knowledge base
    (memories/<house>/notes/), where it is ingested and becomes searchable via
    search_memory. Use for property quirks, access details, owner preferences,
    vendor history, seasonal instructions — anything worth remembering about a
    site outside the inspection flow.

    Args:
        property_name: House code or name the memory is about (e.g. "LBV").
        note: The memory to store, as a clear standalone statement.

    Returns:
        Dict with status and content (S3 URI of the stored note).
    """
    try:
        bucket = _bucket()
        if not bucket:
            return {"status": "error",
                    "content": [{"text": "❌ BEDROCK_KB_S3_BUCKET is not configured."}]}
        slug = _slug(property_name)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        key = f"{_house_prefixes(slug)['notes']}/{stamp}-note.txt"
        body = (f"SITE MEMORY — {property_name}\n"
                f"Recorded: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n{note}")
        s3 = _s3()
        _ensure_house_folders(s3, bucket, slug)
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                      ContentType="text/plain; charset=utf-8")
        _start_ingestion()
        return {"status": "success",
                "content": [{"text": f"🧠 Site memory saved for {property_name}: s3://{bucket}/{key}"}]}
    except Exception as exc:
        return {"status": "error", "content": [{"text": f"❌ Save failed: {exc}"}]}


@tool
def archive_inspection_report(note: str = None) -> Dict[str, Any]:
    """Archive the latest inspection form into the knowledge-base S3 bucket.

    Uploads a plain-text digest under the Bedrock KB data-source prefix (so it
    becomes searchable long-term memory of past inspections) plus the full
    interactive HTML report as a durable artifact, then kicks off a KB
    ingestion job when configured. Use after sign-off, or whenever the
    inspector wants the current state preserved.

    Args:
        note: Optional context to append to the archived summary
            (e.g. "signed off after hot-tub re-clean")

    Returns:
        Dict with status and content (S3 URIs, ingestion job id)
    """
    try:
        if not LATEST_REPORT.exists():
            return {
                "status": "error",
                "content": [{"text": "❌ No exported inspection form found yet — the form "
                                     "exports itself as it changes; make an edit first."}],
            }
        result = archive_report(LATEST_REPORT.read_text(encoding="utf-8"), note=note)
        ingest = (f" Ingestion job `{result['ingestion_job_id']}` started."
                  if result.get("ingestion_job_id") else
                  " KB will pick it up on its next sync.")
        return {
            "status": "success",
            "content": [{
                "text": f"📦 Archived inspection report to the knowledge base bucket.\n"
                        f"- Searchable summary: `{result['summary_uri']}`\n"
                        f"- Full interactive report: `{result['artifact_uri']}`\n"
                        f"- Signed off: {result['signed_off']}.{ingest}"
            }],
        }
    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Archive failed: {e}"}]}


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        print(ensure_folders())
    else:
        print(archive_inspection_report())
