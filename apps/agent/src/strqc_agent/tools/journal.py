"""Journal tool — structured checklist notes writing ``inspection_item_result``.

AGENTS.md §3 (checklist & inspection system), TASKS.md M3.2.
"""

from __future__ import annotations

from strands import tool
from strqc_db import repositories

from ..context import get_context


def _ensure_inspection() -> int:
    """Return the active inspection id, starting one lazily if needed."""
    ctx = get_context()
    if ctx.inspection_id is not None:
        return ctx.inspection_id
    if ctx.task_id is None:
        raise RuntimeError("no active task — cannot start an inspection")
    conn = ctx.get_conn()
    try:
        ctx.inspection_id = repositories.start_inspection(
            conn, ctx.task_id, ctx.checklist_template_id, inspector_id=ctx.stakeholder_id
        )
    finally:
        conn.close()
    return ctx.inspection_id


@tool
def record_checklist_result(item_id: int, result: str, notes: str = "") -> dict:
    """Record a PASS/FAIL/NA verdict for one checklist item on the active inspection.

    Args:
        item_id: The checklist item template id being scored (from list_checklist_items).
        result: One of PASS, FAIL, or NA.
        notes: Optional short observation grounding the verdict.

    Returns:
        The recorded result id and inspection id.
    """
    ctx = get_context()
    inspection_id = _ensure_inspection()
    conn = ctx.get_conn()
    try:
        result_id = repositories.record_item_result(
            conn,
            inspection_id,
            item_id,
            result.strip().upper(),
            notes=notes or None,
            inspector_id=ctx.stakeholder_id,
        )
    finally:
        conn.close()
    return {
        "inspection_item_result_id": result_id,
        "inspection_id": inspection_id,
        "item_id": item_id,
        "result": result.strip().upper(),
    }


@tool
def list_checklist_items() -> list[dict]:
    """List every item on the active checklist template, in walk order.

    Returns:
        Items with id, category, text, and whether a photo is required.
    """
    ctx = get_context()
    conn = ctx.get_conn()
    try:
        items = repositories.checklist_items(conn, ctx.checklist_template_id)
    finally:
        conn.close()
    return [
        {
            "item_id": it["checklist_item_template_id"],
            "category": it["category_name"],
            "text": it["item_text"],
            "required_photo": bool(it["required_photo"]),
        }
        for it in items
    ]
