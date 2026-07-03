"""Versioned SQL migration runner.

Applies ``migrations/NNNN_*.sql`` files in order, recording each in
``schema_migration``. Idempotent: already-applied migrations are skipped.

Usage:
    python -m strqc_db.migrate --db-path ./str_qc.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
from importlib import resources
from pathlib import Path

from .connection import connect

_MIGRATIONS_PACKAGE = "strqc_db.migrations"


def _migration_files() -> list[tuple[str, str]]:
    """Return (name, sql) for every packaged migration, sorted by name."""
    root = resources.files(_MIGRATIONS_PACKAGE)
    out: list[tuple[str, str]] = []
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".sql"):
            out.append((entry.name, entry.read_text(encoding="utf-8")))
    return out


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
          name TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def applied(conn: sqlite3.Connection) -> set[str]:
    _ensure_ledger(conn)
    return {row[0] for row in conn.execute("SELECT name FROM schema_migration")}


def migrate(db_path: str | Path) -> list[str]:
    """Apply pending migrations; return the names applied (in order)."""
    conn = connect(db_path)
    try:
        done = applied(conn)
        ran: list[str] = []
        for name, sql in _migration_files():
            if name in done:
                continue
            with conn:  # transaction per migration
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migration (name) VALUES (?)", (name,))
            ran.append(name)
        return ran
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True, help="Path to the SQLite database")
    args = parser.parse_args()
    ran = migrate(args.db_path)
    if ran:
        for name in ran:
            print(f"applied {name}")
    else:
        print("up to date")


if __name__ == "__main__":
    main()
