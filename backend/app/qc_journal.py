"""QC turnover-inspection journal tool.

The agent records checklist outcomes with this tool while the inspector walks
the property in ANY order. The frontend routes each call to the matching form
item by label (see frontend InspectionView), and — when ``attach_photo`` is
true — attaches the most recent device-camera frame to that same item. Photos
therefore always land on the item being recorded at that moment.
"""

from strands import tool

_VALID_RESULTS = ("PASS", "FAIL", "NA")
_VALID_TAGS = ("before", "after", "evidence")


@tool
def record_checklist_result(
    item: str,
    result: str,
    note: str = "",
    attach_photo: bool = False,
    photo_tag: str = "evidence",
) -> str:
    """Record one turnover-inspection checklist item on the live QC form.

    Call once per checklist item, in whatever order the inspector works.
    The form routes the update by the item's label, checks/unchecks it,
    stores the note, and (when attach_photo is true) pins the latest
    device-camera frame to that item.

    Args:
        item: Exact checklist item label, e.g. "Oven is Clean",
            "Towels are displayed", "Hot Tub - Clear".
        result: PASS, FAIL, or NA.
        note: Short inspector note for this item (optional).
        attach_photo: Attach the most recent camera frame to this item.
            Use for every FAIL, anything notable, and all safety items.
        photo_tag: "before", "after", or "evidence" (default).

    Returns:
        str: Confirmation of what was recorded.
    """
    result_upper = result.strip().upper()
    if result_upper not in _VALID_RESULTS:
        return f"Invalid result {result!r} — use PASS, FAIL, or NA."
    tag = photo_tag.strip().lower()
    if tag not in _VALID_TAGS:
        tag = "evidence"
    parts = [f"Recorded {item!r}: {result_upper}"]
    if note:
        parts.append(f"note: {note}")
    if attach_photo:
        parts.append(f"latest camera frame attached as {tag}")
    return " — ".join(parts)
