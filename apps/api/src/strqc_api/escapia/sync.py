"""Escapia → platform sync jobs (TASKS M4.4–M4.8; AGENTS.md Addendum 2).

Design constraint from the spec: ``GetReservationChanges`` is the *only*
delta endpoint. Units / Owners / Housekeeping / WorkOrders have no changes
feed and must be polled — the ``sync_cursor`` table records ``start_version``
for the reservation delta and ``last_polled_at`` for the poll-based resources.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from strqc_db import repositories

from . import endpoints
from .client import EscapiaClient

_PAGE_SIZE = 100
_UNITS_BY_ID_CHUNK = 25

# Platform work_order.priority → Escapia WorkOrder.priority enum
# (spec enum: Urgent | High | Medium | Low | None).
_PRIORITY_TO_ESCAPIA = {"LOW": "Low", "MEDIUM": "Medium", "HIGH": "High", "URGENT": "Urgent"}

# Platform work_order.status → Escapia WorkOrder.status enum
# (spec enum: Pending | Started | Completed | Assigned | Entered | Approved | Scheduled | Posted).
_STATUS_TO_ESCAPIA = {
    "NEW": "Pending",
    "ASSIGNED": "Assigned",
    "IN_PROGRESS": "Started",
    "BLOCKED": "Pending",
    "DONE": "Completed",
    "CANCELLED": "Pending",  # Escapia has no cancelled status; use active=False instead
}


def _utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    unknown_units: list[str] = field(default_factory=list)


# ── reservations (delta; M4.4) ───────────────────────────────────────────────


def _find_property_by_unit(
    conn: sqlite3.Connection, pmc_id: str, unit_native_pms_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT property_id, unit_code FROM property
        WHERE escapia_unit_native_pms_id = ?
          AND (escapia_pmc_id = ? OR escapia_pmc_id IS NULL)
        """,
        (unit_native_pms_id, pmc_id),
    ).fetchone()
    return dict(row) if row else None


def _upsert_reservation_task(
    conn: sqlite3.Connection, property_id: int, res: endpoints.Reservation, result: SyncResult
) -> None:
    existing = conn.execute(
        "SELECT task_id FROM task WHERE escapia_reservation_native_pms_id = ?",
        (res.native_pms_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE task SET property_id = ?, arrival_date = ?, updated_at = datetime('now')
            WHERE task_id = ?
            """,
            (property_id, res.arrival_date, existing["task_id"]),
        )
        result.updated += 1
    else:
        conn.execute(
            """
            INSERT INTO task (property_id, arrival_date, source_system,
                              escapia_reservation_native_pms_id)
            VALUES (?, ?, 'ESCAPIA', ?)
            """,
            (property_id, res.arrival_date, res.native_pms_id),
        )
        result.created += 1


async def sync_reservations(
    conn: sqlite3.Connection, client: EscapiaClient, pmc_id: str
) -> SyncResult:
    """Drain the reservation delta feed and upsert tasks.

    Advances ``sync_cursor.start_version`` **only after** every fetched change
    has been applied successfully (idempotent upserts make replays safe).
    """
    result = SyncResult()
    cursor = repositories.get_sync_cursor(conn, pmc_id, "RESERVATIONS")
    start = int(cursor["start_version"]) if cursor and cursor["start_version"] is not None else 0

    while True:
        change_list = await endpoints.get_reservation_changes(client, start_version=start)
        if not change_list.changes:
            break
        with conn:
            for change in change_list.changes:
                if "DELET" in change.change_type.upper():
                    result.skipped += 1
                    continue
                res = await endpoints.get_reservation_by_id(client, change.native_pms_id)
                if not res.unit_native_pms_id:
                    result.skipped += 1
                    continue
                prop = _find_property_by_unit(conn, pmc_id, res.unit_native_pms_id)
                if prop is None:
                    result.unknown_units.append(res.unit_native_pms_id)
                    result.skipped += 1
                    continue
                _upsert_reservation_task(conn, prop["property_id"], res, result)
        if change_list.end_version <= start:
            break  # defensive: feed did not advance
        start = change_list.end_version

    repositories.upsert_sync_cursor(conn, pmc_id, "RESERVATIONS", start_version=start)
    return result


# ── units (poll; M4.5) ───────────────────────────────────────────────────────

# Escapia's Unit record is authoritative for demographics only. These columns
# are platform-owned and must NEVER be overwritten by sync (M4.5):
#   standing_instructions, cluster_id, qc_assignee_stakeholder_id,
#   wifi_* / door_code_* secrets.
_UNIT_DEMOGRAPHIC_UPDATE = """
UPDATE property SET
  display_name = COALESCE(?, display_name),
  address_line_1 = COALESCE(?, address_line_1),
  city = COALESCE(?, city),
  state_province = COALESCE(?, state_province),
  postal_code = COALESCE(?, postal_code),
  escapia_unit_native_pms_id = ?,
  escapia_pmc_id = ?,
  source_system = 'ESCAPIA',
  updated_at = datetime('now')
WHERE property_id = ?
"""


async def sync_units(conn: sqlite3.Connection, client: EscapiaClient, pmc_id: str) -> SyncResult:
    """Poll all unit summaries, fetch full Unit records, upsert demographics."""
    result = SyncResult()

    native_ids: list[str] = []
    page = 1
    while True:
        paged = await endpoints.search_unit_summaries(
            client, page_number=page, page_size=_PAGE_SIZE
        )
        native_ids.extend(u.native_pms_id for u in paged.results if u.native_pms_id)
        if not paged.results or len(native_ids) >= paged.total_count:
            break
        page += 1

    for i in range(0, len(native_ids), _UNITS_BY_ID_CHUNK):
        units = await endpoints.get_units_by_id(client, native_ids[i : i + _UNITS_BY_ID_CHUNK])
        with conn:
            for unit in units:
                if not unit.native_pms_id:
                    result.skipped += 1
                    continue
                row = conn.execute(
                    "SELECT property_id FROM property "
                    "WHERE escapia_pmc_id = ? AND escapia_unit_native_pms_id = ?",
                    (pmc_id, unit.native_pms_id),
                ).fetchone()
                if row is None and unit.unit_code:
                    # First sync: adopt an existing platform property by unit code.
                    row = conn.execute(
                        "SELECT property_id FROM property WHERE unit_code = ?", (unit.unit_code,)
                    ).fetchone()
                if row is not None:
                    conn.execute(
                        _UNIT_DEMOGRAPHIC_UPDATE,
                        (
                            unit.unit_name,
                            unit.address_line_1,
                            unit.city,
                            unit.state_province,
                            unit.postal_code,
                            unit.native_pms_id,
                            pmc_id,
                            row["property_id"],
                        ),
                    )
                    result.updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO property
                          (unit_code, display_name, address_line_1, city, state_province,
                           postal_code, escapia_unit_native_pms_id, escapia_pmc_id, source_system)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ESCAPIA')
                        """,
                        (
                            unit.unit_code or unit.native_pms_id,
                            unit.unit_name,
                            unit.address_line_1,
                            unit.city,
                            unit.state_province,
                            unit.postal_code,
                            unit.native_pms_id,
                            pmc_id,
                        ),
                    )
                    result.created += 1

    repositories.upsert_sync_cursor(conn, pmc_id, "UNITS", last_polled_at=_utcnow())
    return result


# ── owners (poll; M4.6) ──────────────────────────────────────────────────────


async def sync_owners(conn: sqlite3.Connection, client: EscapiaClient, pmc_id: str) -> SyncResult:
    """Poll owners; upsert OWNER stakeholders and link owner↔unit roles."""
    result = SyncResult()
    role_row = conn.execute("SELECT role_id FROM role WHERE role_key = 'OWNER'").fetchone()
    if role_row is None:
        raise RuntimeError("role OWNER missing — run migrations/seed first")
    owner_role_id = role_row["role_id"]

    page = 1
    fetched = 0
    while True:
        owners, total = await endpoints.search_owners(client, page_number=page, page_size=_PAGE_SIZE)
        if not owners:
            break
        fetched += len(owners)
        with conn:
            for owner in owners:
                if not owner.native_pms_id:
                    result.skipped += 1
                    continue
                row = conn.execute(
                    "SELECT stakeholder_id FROM stakeholder WHERE escapia_owner_native_pms_id = ?",
                    (owner.native_pms_id,),
                ).fetchone()
                if row is not None:
                    stakeholder_id = row["stakeholder_id"]
                    conn.execute(
                        "UPDATE stakeholder SET full_name = ?, email = COALESCE(?, email), "
                        "phone = COALESCE(?, phone) WHERE stakeholder_id = ?",
                        (owner.full_name, owner.email, owner.phone, stakeholder_id),
                    )
                    result.updated += 1
                else:
                    cur = conn.execute(
                        "INSERT INTO stakeholder (full_name, email, phone, "
                        "escapia_owner_native_pms_id) VALUES (?, ?, ?, ?)",
                        (owner.full_name, owner.email, owner.phone, owner.native_pms_id),
                    )
                    stakeholder_id = int(cur.lastrowid)
                    result.created += 1
                # ownsUnitNativePMSIDs gives owner↔unit linkage directly (Addendum 2).
                for unit_native_id in owner.owns_unit_native_pms_ids:
                    prop = _find_property_by_unit(conn, pmc_id, unit_native_id)
                    if prop is None:
                        result.unknown_units.append(unit_native_id)
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO stakeholder_role "
                        "(stakeholder_id, role_id, property_id) VALUES (?, ?, ?)",
                        (stakeholder_id, owner_role_id, prop["property_id"]),
                    )
        if fetched >= total:
            break
        page += 1

    repositories.upsert_sync_cursor(conn, pmc_id, "OWNERS", last_polled_at=_utcnow())
    return result


# ── housekeeping status map + write-back (M4.7) ──────────────────────────────


async def load_housekeeping_status_map(
    conn: sqlite3.Connection,
    client: EscapiaClient,
    pmc_id: str,
    *,
    stage_to_status_name: dict[str, str] | None = None,
) -> int:
    """Load the PMC-specific status lookup into ``housekeeping_status_map``.

    Status IDs are PMC-configurable — never hardcoded (Addendum 2). Default
    heuristic: the status flagged ``isDefaultOnCheckIn`` (guest-ready) maps to
    stage ``DONE``; ``isDefaultOnCheckOut`` (dirty) maps to stage ``CLN``.
    ``stage_to_status_name`` overrides by (case-insensitive) status name.
    """
    statuses = await endpoints.get_housekeeping_status_list(client)
    by_name = {(s.name or "").lower(): s for s in statuses}

    picks: dict[str, endpoints.HousekeepingStatus] = {}
    for stage_key, name in (stage_to_status_name or {}).items():
        status = by_name.get(name.lower())
        if status is None:
            raise LookupError(f"no Escapia housekeeping status named {name!r} for this PMC")
        picks[stage_key] = status
    if "DONE" not in picks:
        ready = next((s for s in statuses if s.is_default_on_check_in), None)
        if ready is not None:
            picks["DONE"] = ready
    if "CLN" not in picks:
        dirty = next((s for s in statuses if s.is_default_on_check_out), None)
        if dirty is not None:
            picks["CLN"] = dirty

    written = 0
    with conn:
        for stage_key, status in picks.items():
            stage = conn.execute(
                "SELECT stage_definition_id FROM stage_definition WHERE stage_key = ?", (stage_key,)
            ).fetchone()
            if stage is None:
                continue
            conn.execute(
                """
                INSERT INTO housekeeping_status_map
                  (pmc_id, stage_definition_id, escapia_clean_status_id, escapia_status_label)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (pmc_id, stage_definition_id) DO UPDATE SET
                  escapia_clean_status_id = excluded.escapia_clean_status_id,
                  escapia_status_label = excluded.escapia_status_label,
                  updated_at = datetime('now')
                """,
                (pmc_id, stage["stage_definition_id"], status.native_pms_id, status.name),
            )
            written += 1
    repositories.upsert_sync_cursor(conn, pmc_id, "HOUSEKEEPING", last_polled_at=_utcnow())
    return written


async def push_housekeeping_ready(
    conn: sqlite3.Connection, client: EscapiaClient, pmc_id: str, task_id: int
) -> bool:
    """Write the guest-ready status back to Escapia for a task's unit (M4.7)."""
    task = conn.execute(
        """
        SELECT t.task_id, p.escapia_unit_native_pms_id
        FROM task t JOIN property p ON p.property_id = t.property_id
        WHERE t.task_id = ?
        """,
        (task_id,),
    ).fetchone()
    if task is None:
        raise LookupError(f"task {task_id} not found")
    if not task["escapia_unit_native_pms_id"]:
        raise LookupError(f"task {task_id}: property has no escapia_unit_native_pms_id")

    mapped = conn.execute(
        """
        SELECT m.escapia_clean_status_id, m.escapia_status_label
        FROM housekeeping_status_map m
        JOIN stage_definition sd ON sd.stage_definition_id = m.stage_definition_id
        WHERE m.pmc_id = ? AND sd.stage_key = 'DONE'
        """,
        (pmc_id,),
    ).fetchone()
    if mapped is None:
        raise LookupError(
            f"no housekeeping status mapped for stage DONE (pmc {pmc_id}); "
            "run load_housekeeping_status_map first — status IDs are never hardcoded"
        )

    return await endpoints.save_unit_housekeeping_status(
        client,
        native_unit_id=task["escapia_unit_native_pms_id"],
        status_native_pms_id=mapped["escapia_clean_status_id"],
        status_name=mapped["escapia_status_label"],
    )


# ── work orders (write; M4.8) ────────────────────────────────────────────────


async def push_work_order(
    conn: sqlite3.Connection, client: EscapiaClient, pmc_id: str, work_order_id: int
) -> str:
    """Push a platform work order to Escapia via SaveWorkOrder; store the native id."""
    row = conn.execute(
        """
        SELECT wo.*, p.unit_code, p.escapia_unit_native_pms_id
        FROM work_order wo JOIN property p ON p.property_id = wo.property_id
        WHERE wo.work_order_id = ?
        """,
        (work_order_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"work order {work_order_id} not found")
    wo = dict(row)
    if not wo["escapia_unit_native_pms_id"]:
        raise LookupError(f"work order {work_order_id}: property has no escapia_unit_native_pms_id")

    payload: dict[str, Any] = {
        # MaintenanceUnitSummary — nativePMSID identifies the unit.
        "unit": {"nativePMSID": wo["escapia_unit_native_pms_id"], "code": wo["unit_code"]},
        "description": wo["details"] or "",
        "priority": _PRIORITY_TO_ESCAPIA.get(wo["priority"], "Medium"),
        "status": _STATUS_TO_ESCAPIA.get(wo["status"], "Pending"),
        "active": wo["status"] != "CANCELLED",
        "isInternal": True,
    }
    if wo["escapia_work_order_native_pms_id"]:
        payload["nativePMSID"] = wo["escapia_work_order_native_pms_id"]

    saved = await endpoints.save_work_order(client, payload)
    native_id = str(saved.get("nativePMSID") or "")
    if native_id:
        with conn:
            conn.execute(
                "UPDATE work_order SET escapia_work_order_native_pms_id = ? WHERE work_order_id = ?",
                (native_id, work_order_id),
            )
    return native_id
