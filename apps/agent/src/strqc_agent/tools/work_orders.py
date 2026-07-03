"""Work order tools — issue routing from failed checklist items (AGENTS.md §5)."""

from __future__ import annotations

from strands import tool
from strqc_db import repositories

from ..context import get_context


@tool
def open_work_order(
    details: str,
    priority: str = "MEDIUM",
    source_item_result_ids: list[int] | None = None,
) -> dict:
    """Open a work order for facilities on the active property.

    Args:
        details: What is broken/missing and where; enough for facilities to act.
        priority: LOW, MEDIUM, HIGH, or URGENT.
        source_item_result_ids: Failed inspection item result ids that triggered this.

    Returns:
        The created work order id, priority, and status.
    """
    ctx = get_context()
    if ctx.property_id is None:
        raise RuntimeError("no active property — cannot open a work order")
    conn = ctx.get_conn()
    try:
        wo_id = repositories.create_work_order(
            conn,
            property_id=ctx.property_id,
            task_id=ctx.task_id,
            details=details,
            priority=priority.strip().upper(),
            source_item_result_ids=source_item_result_ids,
        )
    finally:
        conn.close()
    return {"work_order_id": wo_id, "priority": priority.strip().upper(), "status": "NEW"}


@tool
def list_open_work_orders() -> list[dict]:
    """List work orders still open for the active property (all properties if none active).

    Returns:
        Open work orders with id, priority, status, and details.
    """
    ctx = get_context()
    sql = (
        "SELECT work_order_id, property_id, task_id, status, priority, details, opened_at "
        "FROM work_order WHERE status NOT IN ('DONE', 'CANCELLED')"
    )
    params: tuple = ()
    if ctx.property_id is not None:
        sql += " AND property_id = ?"
        params = (ctx.property_id,)
    conn = ctx.get_conn()
    try:
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY opened_at", params)]
    finally:
        conn.close()
    return rows
