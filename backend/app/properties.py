"""Read-only lookups for the inspection form's roster + QC inspector pickers.

The inspection form (public/inspection.html) needs two selectable lists:
  - which home is being inspected (the property dropdown), and
  - who the QC inspector signing off is.

Both come straight from the shared STRQC sqlite database. This module keeps
the queries in one place; the DB path resolves the same way report_db does so
the backend (cwd = backend/workspace) and the strqc packages share one file.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _db_path() -> Path:
    raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def list_properties() -> List[Dict[str, Any]]:
    """Active homes for the inspection dropdown, ordered by display name.

    Returns identity + address + door code so the form header can fully
    rehydrate when a different home is selected. Falls back to the unit code
    for the label when a home has no display name yet.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT p.property_id,
                       p.unit_code,
                       p.display_name,
                       p.address_line_1,
                       p.city,
                       p.state_province,
                       p.postal_code,
                       c.name AS cluster,
                       s.full_name AS qc_assignee
                  FROM property p
                  LEFT JOIN cluster c ON p.cluster_id = c.cluster_id
                  LEFT JOIN stakeholder s ON p.qc_assignee_stakeholder_id = s.stakeholder_id
                 WHERE p.roster_active = 1
                 ORDER BY COALESCE(NULLIF(p.display_name, ''), p.unit_code)
                """
            ).fetchall()
    except Exception:
        return []

    properties: List[Dict[str, Any]] = []
    for row in rows:
        unit_code = row["unit_code"] or ""
        name = (row["display_name"] or "").strip() or unit_code
        address_parts = [
            (row["address_line_1"] or "").strip(),
            (row["city"] or "").strip(),
            (row["state_province"] or "").strip(),
            (row["postal_code"] or "").strip(),
        ]
        address = ", ".join(part for part in address_parts if part)
        properties.append(
            {
                "id": row["property_id"],
                "unitCode": unit_code,
                "name": name,
                "address": address,
                "cluster": (row["cluster"] or "").strip(),
                "qcAssignee": (row["qc_assignee"] or "").strip(),
            }
        )
    return properties


def list_inspectors() -> List[Dict[str, Any]]:
    """Stakeholders who can sign off a QC inspection.

    Prefers those carrying a QC / inspector / property-manager role, but falls
    back to the full stakeholder roster if role wiring is absent so the picker
    is never empty.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT s.stakeholder_id, s.full_name
                  FROM stakeholder s
                  JOIN stakeholder_role sr ON s.stakeholder_id = sr.stakeholder_id
                  JOIN role r ON sr.role_id = r.role_id
                 WHERE r.role_key IN ('QC_INSPECTOR', 'PROPERTY_MANAGER')
                    OR UPPER(r.role_name) LIKE '%QC%'
                    OR UPPER(r.role_name) LIKE '%INSPECT%'
                    OR UPPER(r.role_name) LIKE '%PROPERTY MANAGER%'
                 ORDER BY s.full_name
                """
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT stakeholder_id, full_name FROM stakeholder ORDER BY full_name"
                ).fetchall()
    except Exception:
        return []

    return [
        {"id": row["stakeholder_id"], "name": (row["full_name"] or "").strip()}
        for row in rows
        if (row["full_name"] or "").strip()
    ]
