#!/usr/bin/env python3
"""Export legacy SQLite rows as deterministic JSONL for PostgreSQL loading.

This utility is deliberately non-destructive. It preserves source table/row
identity and raw values, allowing a reviewed loader to map properties while
leaving historical inspections readable without fabricated rooms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

PRESERVED_TABLES = (
    "property", "task", "stakeholder", "role", "stakeholder_role", "cluster",
    "inspection_reports",
)


def export(source: Path, destination: Path) -> dict[str, dict[str, object]]:
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    summary: dict[str, dict[str, object]] = {}
    with destination.open("w", encoding="utf-8") as output:
        for table in PRESERVED_TABLES:
            if table not in existing:
                summary[table] = {"count": 0, "missing": True}
                continue
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                record = {"source_table": table, "source_row": dict(row)}
                line = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
                output.write(line + "\n")
                digest.update((line + "\n").encode())
                count += 1
            summary[table] = {"count": count, "sha256": digest.hexdigest()}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    summary = export(args.source.resolve(), args.destination.resolve())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

