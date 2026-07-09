"""Tenant-scoped CSV onboarding import.

Reuses the proven ``scripts/migrate_phase1.Migrator`` parsing/validation
verbatim — this module only threads the target ``tenant_id`` and returns the
accumulated ``migration_issue`` records as JSON for the onboarding UI.

Two entry points mirror the CLI's two ingest passes:
  * ``import_roster``  -> Migrator.ingest_roster
  * ``import_master``  -> Migrator.ingest_master (needs the tenant's existing
    property map so master rows link to the right property_id).
"""

from __future__ import annotations

import csv
import io
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Reuse the CLI importer (single source of column handling / validation).
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from migrate_phase1 import Migrator  # noqa: E402


def _db_path() -> Path:
    import os

    raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_temp_csv(content: bytes) -> Path:
    import tempfile

    tmp = tempfile.NamedTemporaryFile(
        prefix="strqc-import-", suffix=".csv", delete=False, mode="wb"
    )
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _issues_json(migrator: Migrator) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for issue in migrator.issues:
        out.append(
            {
                "type": issue.issue_type,
                "severity": issue.severity,
                "source": issue.source_name,
                "row": issue.row_number,
                "propertyCode": issue.property_code,
                "message": issue.message,
            }
        )
    return out


def _tenant_property_map(conn: sqlite3.Connection, tenant_id: int) -> Dict[str, int]:
    rows = conn.execute(
        "SELECT unit_code, property_id FROM property WHERE tenant_id = ?", (tenant_id,)
    ).fetchall()
    return {str(r["unit_code"]).strip().upper(): int(r["property_id"]) for r in rows}


def _count_rows(content: bytes) -> int:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    return max(0, len(rows) - 1)  # minus header


def import_roster(content: bytes, tenant_id: int) -> Dict[str, Any]:
    """Ingest an address-roster CSV scoped to ``tenant_id``."""
    tmp = _write_temp_csv(content)
    conn = _connect()
    try:
        migrator = Migrator(conn, tenant_id=tenant_id)
        migrator.seed_template()
        property_ids = migrator.ingest_roster(tmp)
        migrator.persist_issues()
        conn.commit()
        issues = _issues_json(migrator)
        return {
            "kind": "roster",
            "rowsParsed": _count_rows(content),
            "propertiesUpserted": len(property_ids),
            "errors": sum(1 for i in issues if i["severity"] == "ERROR"),
            "warnings": sum(1 for i in issues if i["severity"] == "WARN"),
            "issues": issues,
        }
    finally:
        conn.close()
        try:
            tmp.unlink()
        except OSError:
            pass


def import_master(content: bytes, tenant_id: int) -> Dict[str, Any]:
    """Ingest a master-checklist CSV scoped to ``tenant_id``.

    Links task rows to the tenant's existing properties (seeded by a prior
    roster import); unknown codes create stub properties for this tenant, as
    the CLI does.
    """
    tmp = _write_temp_csv(content)
    conn = _connect()
    try:
        migrator = Migrator(conn, tenant_id=tenant_id)
        migrator.seed_template()
        property_map = _tenant_property_map(conn, tenant_id)
        task_counts = migrator.ingest_master(tmp, property_map)
        migrator.flag_roster_only_properties(property_map, task_counts)
        migrator.persist_issues()
        conn.commit()
        issues = _issues_json(migrator)
        return {
            "kind": "master",
            "rowsParsed": _count_rows(content),
            "tasksCreated": sum(task_counts.values()),
            "errors": sum(1 for i in issues if i["severity"] == "ERROR"),
            "warnings": sum(1 for i in issues if i["severity"] == "WARN"),
            "issues": issues,
        }
    finally:
        conn.close()
        try:
            tmp.unlink()
        except OSError:
            pass
