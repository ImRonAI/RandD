"""Thin repository layer over the operational schema.

Only the queries the agent, domain services, and API actually need.
All functions take an open connection (see :mod:`strqc_db.connection`).
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


# ── properties ───────────────────────────────────────────────────────────────


def get_property(conn: sqlite3.Connection, unit_code: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM property WHERE unit_code = ?", (unit_code,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_properties(conn: sqlite3.Connection, *, active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM property"
    if active_only:
        sql += " WHERE roster_active = 1"
    return _rows(conn.execute(sql + " ORDER BY unit_code"))


def property_features(conn: sqlite3.Connection, property_id: int) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT pf.*, ft.feature_key, ft.feature_name
            FROM property_feature pf
            JOIN property_feature_type ft ON ft.feature_type_id = pf.feature_type_id
            WHERE pf.property_id = ?
            ORDER BY ft.feature_name, pf.location_label
            """,
            (property_id,),
        )
    )


# ── tasks & stages ───────────────────────────────────────────────────────────


def tasks_for_date(conn: sqlite3.Connection, arrival_date: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT t.*, p.unit_code, p.display_name, p.cluster_id,
                   sd.stage_key AS current_stage_key
            FROM task t
            JOIN property p ON p.property_id = t.property_id
            LEFT JOIN stage_definition sd
              ON sd.stage_definition_id = t.current_stage_definition_id
            WHERE t.arrival_date = ?
            ORDER BY p.cluster_id, t.arrival_date
            """,
            (arrival_date,),
        )
    )


def set_task_stage(conn: sqlite3.Connection, task_id: int, stage_key: str,
                   completed_by: int | None = None) -> None:
    """Advance a task to a stage and record the stage event."""
    row = conn.execute(
        "SELECT stage_definition_id FROM stage_definition WHERE stage_key = ?", (stage_key,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown stage_key {stage_key!r}")
    stage_id = row[0]
    with conn:
        conn.execute(
            "UPDATE task SET current_stage_definition_id = ?, updated_at = datetime('now') "
            "WHERE task_id = ?",
            (stage_id, task_id),
        )
        conn.execute(
            """
            INSERT INTO task_stage_event (task_id, stage_definition_id, is_complete, completed_at,
                                          completed_by_stakeholder_id)
            VALUES (?, ?, 1, datetime('now'), ?)
            ON CONFLICT (task_id, stage_definition_id)
            DO UPDATE SET is_complete = 1, completed_at = datetime('now'),
                          completed_by_stakeholder_id = excluded.completed_by_stakeholder_id
            """,
            (task_id, stage_id, completed_by),
        )


# ── inspections ──────────────────────────────────────────────────────────────


def start_inspection(conn: sqlite3.Connection, task_id: int, checklist_template_id: int,
                     inspector_id: int | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO inspection (task_id, checklist_template_id, inspector_stakeholder_id, "
            "started_at) VALUES (?, ?, ?, datetime('now'))",
            (task_id, checklist_template_id, inspector_id),
        )
    return int(cur.lastrowid)


def record_item_result(conn: sqlite3.Connection, inspection_id: int, item_template_id: int,
                       result: str, *, notes: str | None = None,
                       photo_memory_id: int | None = None,
                       inspector_id: int | None = None) -> int:
    if result not in ("PASS", "FAIL", "NA"):
        raise ValueError(f"invalid result {result!r}")
    with conn:
        cur = conn.execute(
            """
            INSERT INTO inspection_item_result
              (inspection_id, checklist_item_template_id, result, notes, photo_memory_id,
               inspector_stakeholder_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (inspection_id, item_template_id, result, notes, photo_memory_id, inspector_id),
        )
    return int(cur.lastrowid)


def checklist_items(conn: sqlite3.Connection, checklist_template_id: int) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT it.*, c.category_name, c.display_order AS category_order
            FROM checklist_item_template it
            JOIN checklist_category c ON c.checklist_category_id = it.checklist_category_id
            WHERE c.checklist_template_id = ?
            ORDER BY c.display_order, it.display_order
            """,
            (checklist_template_id,),
        )
    )


# ── photos ───────────────────────────────────────────────────────────────────


def add_photo(conn: sqlite3.Connection, *, property_id: int | None, task_id: int | None,
              inspection_id: int | None, uri: str, caption: str | None = None,
              content_hash: str | None = None, include_in_report: bool = False,
              metadata_json: str | None = None) -> int:
    with conn:
        cur = conn.execute(
            """
            INSERT INTO photo_memory
              (property_id, task_id, inspection_id, uri, caption, content_hash,
               include_in_report, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (property_id, task_id, inspection_id, uri, caption, content_hash,
             int(include_in_report), metadata_json),
        )
    return int(cur.lastrowid)


# ── work orders ──────────────────────────────────────────────────────────────


def create_work_order(conn: sqlite3.Connection, *, property_id: int, task_id: int | None,
                      details: str, priority: str = "MEDIUM",
                      source_item_result_ids: list[int] | None = None) -> int:
    if priority not in ("LOW", "MEDIUM", "HIGH", "URGENT"):
        raise ValueError(f"invalid priority {priority!r}")
    with conn:
        cur = conn.execute(
            "INSERT INTO work_order (task_id, property_id, status, priority, details) "
            "VALUES (?, ?, 'NEW', ?, ?)",
            (task_id, property_id, priority, details),
        )
        wo_id = int(cur.lastrowid)
        for item_id in source_item_result_ids or []:
            conn.execute(
                "INSERT INTO work_order_source_item (work_order_id, inspection_item_result_id) "
                "VALUES (?, ?)",
                (wo_id, item_id),
            )
    return wo_id


# ── sync cursors & housekeeping map (Addendum 2) ─────────────────────────────


def get_sync_cursor(conn: sqlite3.Connection, pmc_id: str, resource: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM sync_cursor WHERE pmc_id = ? AND resource = ?", (pmc_id, resource)
    ).fetchone()
    return dict(row) if row else None


def upsert_sync_cursor(conn: sqlite3.Connection, pmc_id: str, resource: str, *,
                       start_version: int | None = None,
                       last_polled_at: str | None = None) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO sync_cursor (pmc_id, resource, start_version, last_polled_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (pmc_id, resource) DO UPDATE SET
              start_version = COALESCE(excluded.start_version, sync_cursor.start_version),
              last_polled_at = COALESCE(excluded.last_polled_at, sync_cursor.last_polled_at),
              updated_at = datetime('now')
            """,
            (pmc_id, resource, start_version, last_polled_at),
        )
