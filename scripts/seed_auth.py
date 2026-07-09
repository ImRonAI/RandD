#!/usr/bin/env python3
"""One-time seeding of the first auth users.

Creates:
  * the platform super-admin (tenant_id NULL, is_platform_admin=1), and
  * RandD Tradesmen's first tenant admin (tenant_id=1).

Passwords are supplied via environment variables or interactive prompt and are
hashed with passlib (bcrypt) before storage. Plaintext is never written or
logged.

Env vars (optional; prompted if absent):
  STRQC_SUPERADMIN_EMAIL / STRQC_SUPERADMIN_PASSWORD
  STRQC_RANDD_ADMIN_EMAIL / STRQC_RANDD_ADMIN_PASSWORD

Usage:
  python scripts/seed_auth.py --db-path ./str_qc.sqlite
"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Make the backend package importable so we reuse its password hashing.
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.auth import hash_password  # noqa: E402


def _resolve_db_path(db_path: str) -> Path:
    raw = Path(db_path)
    return raw if raw.is_absolute() else _REPO_ROOT / raw


def _get_secret(env_key: str, prompt: str) -> str:
    value = os.getenv(env_key)
    if value:
        return value
    return getpass.getpass(prompt)


def _upsert_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    tenant_id: int | None,
    is_platform_admin: int,
) -> str:
    existing = conn.execute(
        "SELECT user_id FROM app_user WHERE email = ?", (email,)
    ).fetchone()
    pw_hash = hash_password(password)
    if existing:
        conn.execute(
            """
            UPDATE app_user
               SET password_hash = ?, tenant_id = ?, is_platform_admin = ?, is_active = 1
             WHERE email = ?
            """,
            (pw_hash, tenant_id, is_platform_admin, email),
        )
        return f"updated existing user {email}"
    conn.execute(
        """
        INSERT INTO app_user (tenant_id, email, password_hash, is_platform_admin)
        VALUES (?, ?, ?, ?)
        """,
        (tenant_id, email, pw_hash, is_platform_admin),
    )
    return f"created user {email}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the first auth users.")
    parser.add_argument(
        "--db-path",
        default=os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"),
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--skip-superadmin", action="store_true", help="Do not create the platform super-admin."
    )
    parser.add_argument(
        "--skip-randd", action="store_true", help="Do not create the RandD tenant admin."
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    db_path = _resolve_db_path(args.db_path)
    if not db_path.exists():
        print(f"error: database not found at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        # Verify the auth schema exists (migration must have run first).
        try:
            conn.execute("SELECT 1 FROM app_user LIMIT 1")
        except sqlite3.OperationalError:
            print(
                "error: app_user table missing — run the 0003 migration first",
                file=sys.stderr,
            )
            return 1

        if not args.skip_superadmin:
            sa_email = os.getenv("STRQC_SUPERADMIN_EMAIL") or input(
                "Platform super-admin email: "
            ).strip()
            sa_pw = _get_secret(
                "STRQC_SUPERADMIN_PASSWORD", "Platform super-admin password: "
            )
            msg = _upsert_user(
                conn,
                email=sa_email,
                password=sa_pw,
                tenant_id=None,
                is_platform_admin=1,
            )
            print(f"[seed] super-admin: {msg}")

        if not args.skip_randd:
            trow = conn.execute(
                "SELECT tenant_id FROM tenant WHERE tenant_id = 1"
            ).fetchone()
            if not trow:
                print(
                    "error: tenant_id=1 (RandD Tradesmen) missing — migration incomplete",
                    file=sys.stderr,
                )
                return 1
            ra_email = os.getenv("STRQC_RANDD_ADMIN_EMAIL") or input(
                "RandD tenant admin email: "
            ).strip()
            ra_pw = _get_secret(
                "STRQC_RANDD_ADMIN_PASSWORD", "RandD tenant admin password: "
            )
            msg = _upsert_user(
                conn,
                email=ra_email,
                password=ra_pw,
                tenant_id=1,
                is_platform_admin=0,
            )
            print(f"[seed] RandD admin: {msg}")

        conn.commit()
    finally:
        conn.close()

    print("[seed] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
