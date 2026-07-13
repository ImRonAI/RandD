"""Read-only field-app data, straight from the shared STRQC sqlite database.

Everything the Vantage mobile app shows comes from here — the real task board,
properties, clusters, the Master Checklist, and notification triggers. Nothing
is synthesized. Secrets (door codes / Wi-Fi passwords) are decrypted only when
STRQC_MASTER_KEY is present; otherwise they are reported as locked so the UI
masks them (the same contract as the rest of the platform).

This module is additive integration for the frontend — it does not change any
existing backend behavior.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.qc_journal import CHECKLIST_ITEMS

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _db_path() -> Path:
    raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _reveal(token: Optional[str], unit_code: str) -> Tuple[Optional[str], bool]:
    """(plaintext, present). Decrypts when the master key is available, else
    reports the secret as present-but-locked so the UI masks it."""
    if not token:
        return None, False
    key = os.getenv("STRQC_MASTER_KEY", "")
    if key:
        try:
            from strqc_shared.crypto import decrypt_secret

            for aad in (unit_code, ""):
                try:
                    return decrypt_secret(token, key, aad=aad), True
                except Exception:  # noqa: BLE001 - try next AAD / fall through to locked
                    continue
        except Exception:  # noqa: BLE001 - crypto lib unavailable
            pass
    return None, True


def list_clusters() -> List[Dict[str, Any]]:
    """Real clusters (field areas) with their active-property counts."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT c.cluster_id, c.name,
                       COUNT(p.property_id) FILTER (WHERE p.roster_active = 1) AS units
                  FROM cluster c
                  LEFT JOIN property p ON p.cluster_id = c.cluster_id
                 GROUP BY c.cluster_id, c.name
                 HAVING units > 0
                 ORDER BY units DESC, c.name
                """
            ).fetchall()
    except Exception:
        return []
    return [
        {"id": r["cluster_id"], "name": (r["name"] or "").strip(), "units": r["units"] or 0}
        for r in rows
    ]


def _stage(row: sqlite3.Row) -> Dict[str, Optional[str]]:
    return {"key": row["stage_key"], "name": row["stage_name"]}


def list_day(cluster_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """The real turnover board as the day plan — tasks joined to their property,
    cluster, housekeeper and current stage. Optionally scoped to one cluster."""
    where = "WHERE p.roster_active = 1"
    params: List[Any] = []
    if cluster_id is not None:
        where += " AND p.cluster_id = ?"
        params.append(cluster_id)
    try:
        with _connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.task_id, t.arrival_date,
                       p.property_id, p.unit_code, p.display_name, p.address_line_1,
                       c.name AS cluster,
                       hk.full_name AS housekeeper,
                       qc.full_name AS qc_assignee,
                       sd.stage_key, sd.stage_name
                  FROM task t
                  JOIN property p ON t.property_id = p.property_id
                  LEFT JOIN cluster c ON p.cluster_id = c.cluster_id
                  LEFT JOIN stakeholder hk ON t.assigned_housekeeper_stakeholder_id = hk.stakeholder_id
                  LEFT JOIN stakeholder qc ON p.qc_assignee_stakeholder_id = qc.stakeholder_id
                  LEFT JOIN stage_definition sd ON t.current_stage_definition_id = sd.stage_definition_id
                  {where}
                 ORDER BY (t.arrival_date IS NULL), t.arrival_date, p.unit_code
                """,
                params,
            ).fetchall()
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        unit = r["unit_code"] or ""
        out.append(
            {
                "taskId": r["task_id"],
                "propertyId": r["property_id"],
                "unitCode": unit,
                "name": (r["display_name"] or "").strip() or unit,
                "address": (r["address_line_1"] or "").strip(),
                "cluster": (r["cluster"] or "").strip(),
                "arrivalDate": r["arrival_date"],
                "cleanedBy": (r["housekeeper"] or "").strip(),
                "qcAssignee": (r["qc_assignee"] or "").strip(),
                "stage": _stage(r),
            }
        )
    return out


def property_detail(property_id: int) -> Optional[Dict[str, Any]]:
    """Full real detail for one property, with secrets revealed or locked."""
    try:
        with _connect() as conn:
            r = conn.execute(
                """
                SELECT p.*, c.name AS cluster, s.full_name AS qc_assignee
                  FROM property p
                  LEFT JOIN cluster c ON p.cluster_id = c.cluster_id
                  LEFT JOIN stakeholder s ON p.qc_assignee_stakeholder_id = s.stakeholder_id
                 WHERE p.property_id = ?
                """,
                (property_id,),
            ).fetchone()
    except Exception:
        return None
    if not r:
        return None

    unit = r["unit_code"] or ""
    door, door_present = _reveal(r["door_code_ciphertext"], unit)
    wifi_pw, wifi_present = _reveal(r["wifi_password_ciphertext"], unit)
    return {
        "id": r["property_id"],
        "unitCode": unit,
        "name": (r["display_name"] or "").strip() or unit,
        "address": (r["address_line_1"] or "").strip(),
        "cluster": (r["cluster"] or "").strip(),
        "qcAssignee": (r["qc_assignee"] or "").strip(),
        "wifiSsid": (r["wifi_ssid"] or "").strip(),
        "standingInstructions": (r["standing_instructions"] or "").strip(),
        "doorCode": door,
        "doorCodeLocked": door is None and door_present,
        "wifiPassword": wifi_pw,
        "wifiPasswordLocked": wifi_pw is None and wifi_present,
    }


def checklist() -> List[Dict[str, Any]]:
    """The authoritative Master Checklist (sections + exact item labels)."""
    return [
        {"name": section, "items": list(items)}
        for section, items in CHECKLIST_ITEMS.items()
    ]


def list_notifications() -> List[Dict[str, Any]]:
    """Real notification triggers, resolved to their responsible role."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT nt.event_key, nt.description, r.role_name
                  FROM notification_trigger nt
                  LEFT JOIN role r ON nt.default_role_id = r.role_id
                 ORDER BY nt.trigger_id
                """
            ).fetchall()
    except Exception:
        return []
    return [
        {
            "event": (r["event_key"] or "").strip(),
            "description": (r["description"] or "").strip(),
            "role": (r["role_name"] or "").strip(),
        }
        for r in rows
    ]
