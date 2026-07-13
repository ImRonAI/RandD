#!/usr/bin/env python3
"""Read-only DAH-124 audit of legacy House Keeping report shape."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "app/vantage/schema.py"
_SPEC = importlib.util.spec_from_file_location("vantage_schema_contract", _SCHEMA_PATH)
assert _SPEC and _SPEC.loader
_SCHEMA = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCHEMA)
LEGACY_CHECKLIST_ID_TO_KEY = _SCHEMA.LEGACY_CHECKLIST_ID_TO_KEY


def audit(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    reports = connection.execute("SELECT state_json FROM inspection_reports").fetchall()
    item_ids: set[str] = set()
    photo_count = 0
    max_photos = 0
    for (raw_state,) in reports:
        state = json.loads(raw_state)
        for item in state.get("items", []):
            item_ids.add(str(item.get("id", "")))
            photos = item.get("photos") or []
            photo_count += len(photos)
            max_photos = max(max_photos, len(photos))
    return {
        "report_count": len(reports),
        "distinct_item_ids": len(item_ids),
        "photo_count": photo_count,
        "max_photos_per_item": max_photos,
        "unknown_item_ids": sorted(item_ids - LEGACY_CHECKLIST_ID_TO_KEY.keys()),
        "result_semantics": "checked_boolean_only_no_PASS_FAIL_NA_inference",
        "room_inference": "disabled",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    print(json.dumps(audit(parser.parse_args().database), sort_keys=True))
