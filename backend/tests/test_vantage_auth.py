from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.vantage.auth import AuthError, MagicCodeService, TokenService
from app.vantage.auth_store import SqlChallengeStore, SqlReplayStore
from app.vantage.schema import install_sqlite_schema


class CapturingSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_code(self, email: str, code: str) -> str:
        self.messages.append((email, code))
        return "provider-message-id"


def test_magic_code_is_hashed_single_use_and_attempt_limited() -> None:
    sender = CapturingSender()
    service = MagicCodeService(secret=b"secret", sender=sender, max_attempts=2)
    challenge = service.request("USER@example.com")
    code = sender.messages[0][1]
    assert challenge.code_hash != code
    assert service.verify("user@example.com", code).email == "user@example.com"
    with pytest.raises(AuthError) as replay:
        service.verify("user@example.com", code)
    assert replay.value.code == "code_replayed"


def test_sender_failure_is_not_reported_as_success() -> None:
    class FailingSender:
        def send_code(self, email: str, code: str) -> str:
            raise RuntimeError("gmail unavailable")

    service = MagicCodeService(secret=b"secret", sender=FailingSender())
    with pytest.raises(AuthError) as failure:
        service.request("user@example.com")
    assert failure.value.code == "delivery_failed"


def test_magic_code_resend_is_throttled() -> None:
    sender = CapturingSender()
    service = MagicCodeService(secret=b"secret", sender=sender)
    service.request("user@example.com")
    with pytest.raises(AuthError) as throttled:
        service.request("user@example.com")
    assert throttled.value.code == "resend_throttled"
    assert len(sender.messages) == 1


def test_signed_session_and_single_use_ws_tokens_are_scoped() -> None:
    tokens = TokenService(b"token-secret")
    session = tokens.issue_session("user-a", "org-a", ["INSPECTOR"], ttl=timedelta(minutes=5))
    claims = tokens.verify_session(session)
    assert (claims["sub"], claims["org_id"]) == ("user-a", "org-a")
    ws = tokens.issue_ws_token(session, ttl=timedelta(seconds=30))
    assert tokens.consume_ws_token(ws)["org_id"] == "org-a"
    with pytest.raises(AuthError) as replay:
        tokens.consume_ws_token(ws)
    assert replay.value.code == "token_replayed"
    tokens.revoke_session(session)
    with pytest.raises(AuthError) as revoked:
        tokens.verify_session(session)
    assert revoked.value.code == "session_revoked"


def test_auth_replay_and_challenge_state_can_be_durable(tmp_path) -> None:
    import sqlite3
    db = tmp_path / "auth.sqlite"
    connection = sqlite3.connect(db)
    install_sqlite_schema(connection)
    connect = lambda: sqlite3.connect(db)
    sender = CapturingSender()
    first_process = MagicCodeService(b"secret", sender, store=SqlChallengeStore(connect))
    first_process.request("user@example.com")
    code = sender.messages[-1][1]
    second_process = MagicCodeService(b"secret", sender, store=SqlChallengeStore(connect))
    second_process.verify("user@example.com", code)
    with pytest.raises(AuthError):
        first_process.verify("user@example.com", code)

    tokens_a = TokenService(b"token-secret", SqlReplayStore(connect))
    session = tokens_a.issue_session("user-a", "org-a", ["INSPECTOR"], ttl=timedelta(minutes=5))
    ws = tokens_a.issue_ws_token(session, ttl=timedelta(seconds=30))
    tokens_a.consume_ws_token(ws)
    with pytest.raises(AuthError) as replay:
        TokenService(b"token-secret", SqlReplayStore(connect)).consume_ws_token(ws)
    assert replay.value.code == "token_replayed"
