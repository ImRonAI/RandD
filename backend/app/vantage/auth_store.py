from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from .auth import MagicChallenge


class SqlChallengeStore:
    """Durable DB-API challenge store; works with SQLite fixtures.

    PostgreSQL deployments use the same contract with their driver adapter and
    the `magic_code_challenge` table from migration 0001.
    """

    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self.connect = connect

    def put(self, challenge: MagicChallenge) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO magic_code_challenge(email,code_hash,salt,expires_at,attempts,max_attempts,used_at,provider_message_id) VALUES (?,?,?,?,?,?,?,?)", (
                challenge.email, challenge.code_hash, challenge.salt, challenge.expires_at, challenge.attempts, 5,
                challenge.expires_at if challenge.used else None, challenge.provider_message_id,
            ))

    def get_latest(self, email: str) -> MagicChallenge | None:
        with self.connect() as c:
            c.row_factory = sqlite3.Row
            row = c.execute("SELECT * FROM magic_code_challenge WHERE lower(email)=lower(?) ORDER BY created_at DESC LIMIT 1", (email,)).fetchone()
        if row is None:
            return None
        expires = row["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00")).timestamp()
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        return MagicChallenge(row["email"], row["code_hash"], row["salt"], float(expires), row["attempts"], row["used_at"] is not None, row["provider_message_id"], float(created))

    def update(self, challenge: MagicChallenge) -> None:
        with self.connect() as c:
            c.execute("UPDATE magic_code_challenge SET attempts=?,used_at=? WHERE id=(SELECT id FROM magic_code_challenge WHERE lower(email)=lower(?) ORDER BY created_at DESC LIMIT 1)", (
                challenge.attempts, datetime.now(timezone.utc).isoformat() if challenge.used else None, challenge.email,
            ))


class SqlReplayStore:
    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self.connect = connect

    def consume(self, jti: str, expires_at: int) -> bool:
        try:
            with self.connect() as c:
                c.execute("INSERT INTO revoked_token(jti,kind,expires_at) VALUES (?,?,?)", (jti, "ws", expires_at))
            return True
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                return False
            raise

    def contains(self, jti: str) -> bool:
        with self.connect() as c:
            return c.execute("SELECT 1 FROM revoked_token WHERE jti=?", (jti,)).fetchone() is not None
