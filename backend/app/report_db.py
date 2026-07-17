"""Track inspection forms in the shared STRQC sqlite database.

One row per form instance, keyed by the UUID the form mints for itself
(``state.formId``). The row is upserted on every export the form posts while
being filled out, and stamped with the S3 URIs when the report is archived.

Schema lives in sql/inspection_reports.sql (applied idempotently here).
STRQC_DB_PATH is resolved against the repo root so the backend (whose runtime
cwd is backend/workspace) and the strqc packages share one database file.
"""

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA = _REPO_ROOT / "sql" / "inspection_reports.sql"


def _db_path() -> Path:
    raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    columns = {row[1] for row in conn.execute("PRAGMA table_info(inspection_reports)")}
    if columns and "form_uuid" not in columns:
        conn.execute("DROP TABLE inspection_reports")  # pre-UUID prototype shape
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def _form_uuid(state: Dict[str, Any]) -> str:
    given = state.get("formId")
    if given:
        return str(given)
    # Exports from forms predating formId: stable per property, so repeated
    # exports of the same legacy form collapse into one row.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"strqc-legacy-{state.get('property', 'unknown')}"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def upsert_form(state: Optional[Dict[str, Any]], html_bytes: int) -> Optional[str]:
    """Insert/update the form's row from a live export. Returns the form UUID."""
    try:
        state = state or {}
        form_id = _form_uuid(state)
        items = state.get("items") or []
        now = _now()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO inspection_reports (form_uuid, created_utc, updated_utc,"
                " property, signed_off, items_total, items_done, sections, repairs,"
                " state_json, html_bytes) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(form_uuid) DO UPDATE SET"
                " updated_utc=excluded.updated_utc, property=excluded.property,"
                " signed_off=excluded.signed_off, items_total=excluded.items_total,"
                " items_done=excluded.items_done, sections=excluded.sections,"
                " repairs=excluded.repairs, state_json=excluded.state_json,"
                " html_bytes=excluded.html_bytes",
                (
                    form_id,
                    state.get("createdUtc") or now,
                    now,
                    state.get("property"),
                    1 if state.get("signedOff") else 0,
                    len(items),
                    sum(1 for item in items if item.get("checked")),
                    len(state.get("sections") or []),
                    (state.get("repairs") or "").strip() or None,
                    json.dumps(state, ensure_ascii=False),
                    html_bytes,
                ),
            )
        return form_id
    except Exception:
        return None  # persistence must never break the export path


def record_archive(
    state: Optional[Dict[str, Any]],
    html_bytes: int,
    s3_summary_uri: Optional[str] = None,
    s3_artifact_uri: Optional[str] = None,
) -> Optional[str]:
    """Stamp the form's row with its archive destination. Returns the form UUID."""
    form_id = upsert_form(state, html_bytes)
    if not form_id:
        return None
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE inspection_reports SET archived_utc=?, s3_summary_uri=?,"
                " s3_artifact_uri=? WHERE form_uuid=?",
                (_now(), s3_summary_uri, s3_artifact_uri, form_id),
            )
        return form_id
    except Exception:
        return None
