from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CodeSender(Protocol):
    def send_code(self, email: str, code: str) -> str: ...


class ChallengeStore(Protocol):
    def put(self, challenge: "MagicChallenge") -> None: ...
    def get_latest(self, email: str) -> "MagicChallenge | None": ...
    def update(self, challenge: "MagicChallenge") -> None: ...


class ReplayStore(Protocol):
    def consume(self, jti: str, expires_at: int) -> bool: ...
    def contains(self, jti: str) -> bool: ...


class MemoryChallengeStore:
    def __init__(self) -> None:
        self.items: dict[str, MagicChallenge] = {}

    def put(self, challenge: "MagicChallenge") -> None:
        self.items[challenge.email] = challenge

    def get_latest(self, email: str) -> "MagicChallenge | None":
        return self.items.get(email)

    def update(self, challenge: "MagicChallenge") -> None:
        self.items[challenge.email] = challenge


class MemoryReplayStore:
    def __init__(self) -> None:
        self.items: set[str] = set()

    def consume(self, jti: str, expires_at: int) -> bool:
        if jti in self.items:
            return False
        self.items.add(jti)
        return True

    def contains(self, jti: str) -> bool:
        return jti in self.items


@dataclass(slots=True)
class MagicChallenge:
    email: str
    code_hash: str
    salt: str
    expires_at: float
    attempts: int = 0
    used: bool = False
    provider_message_id: str | None = None
    requested_at: float = 0.0


class MagicCodeService:
    """Magic-code policy with an injected delivery boundary.

    A durable deployment supplies a repository-backed challenge store. The
    default in-memory store exists for local tests and a single-process dev
    server; it never claims delivery when the sender fails.
    """

    def __init__(self, secret: bytes, sender: CodeSender, *, store: ChallengeStore | None = None, ttl: timedelta = timedelta(minutes=10), max_attempts: int = 5, resend_interval: timedelta = timedelta(seconds=60)):
        self.secret, self.sender, self.ttl, self.max_attempts, self.resend_interval = secret, sender, ttl, max_attempts, resend_interval
        self.store = store or MemoryChallengeStore()

    def _digest(self, email: str, code: str, salt: str) -> str:
        return hmac.new(self.secret, f"{email}:{code}:{salt}".encode(), hashlib.sha256).hexdigest()

    def request(self, email: str) -> MagicChallenge:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise AuthError("invalid_email", "A valid email is required")
        prior = self.store.get_latest(email)
        now = time.time()
        if prior is not None and prior.requested_at and now - prior.requested_at < self.resend_interval.total_seconds():
            raise AuthError("resend_throttled", "Wait before requesting another code")
        code, salt = f"{secrets.randbelow(1_000_000):06d}", secrets.token_hex(16)
        challenge = MagicChallenge(email, self._digest(email, code, salt), salt, now + self.ttl.total_seconds(), requested_at=now)
        try:
            challenge.provider_message_id = self.sender.send_code(email, code)
        except Exception as exc:
            raise AuthError("delivery_failed", "The authentication code could not be delivered") from exc
        self.store.put(challenge)
        return challenge

    def verify(self, email: str, code: str) -> MagicChallenge:
        email = email.strip().lower()
        challenge = self.store.get_latest(email)
        if challenge is None:
            raise AuthError("code_not_found", "Request a new code")
        if challenge.used:
            raise AuthError("code_replayed", "This code has already been used")
        if time.time() >= challenge.expires_at:
            raise AuthError("code_expired", "This code has expired")
        if challenge.attempts >= self.max_attempts:
            raise AuthError("attempt_limit", "Too many verification attempts")
        challenge.attempts += 1
        if not hmac.compare_digest(challenge.code_hash, self._digest(email, code, challenge.salt)):
            self.store.update(challenge)
            raise AuthError("invalid_code", "The code is incorrect")
        challenge.used = True
        self.store.update(challenge)
        return challenge


class TokenService:
    def __init__(self, secret: bytes, replay_store: ReplayStore | None = None):
        if len(secret) < 8:
            raise ValueError("token secret must be at least 8 bytes")
        self.secret = secret
        self.replay_store = replay_store or MemoryReplayStore()

    def _encode(self, claims: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()).rstrip(b"=")
        signature = hmac.new(self.secret, body, hashlib.sha256).digest()
        return f"{body.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def _decode(self, token: str, kind: str) -> dict:
        try:
            raw_body, raw_signature = token.split(".", 1)
            body = raw_body.encode()
            signature = base64.urlsafe_b64decode(raw_signature + "=" * (-len(raw_signature) % 4))
            if not hmac.compare_digest(signature, hmac.new(self.secret, body, hashlib.sha256).digest()):
                raise ValueError
            claims = json.loads(base64.urlsafe_b64decode(raw_body + "=" * (-len(raw_body) % 4)))
        except Exception as exc:
            raise AuthError("invalid_token", "The token is invalid") from exc
        if claims.get("kind") != kind or time.time() >= claims.get("exp", 0):
            raise AuthError("token_expired", "The token is expired or invalid")
        return claims

    def issue_session(self, user_id: str, organization_id: str, roles: list[str], *, ttl: timedelta) -> str:
        now = int(time.time())
        return self._encode({"kind": "session", "sub": user_id, "org_id": organization_id, "roles": roles, "iat": now, "exp": now + int(ttl.total_seconds()), "jti": str(uuid.uuid4())})

    def verify_session(self, token: str) -> dict:
        claims = self._decode(token, "session")
        if self.replay_store.contains(claims["jti"]):
            raise AuthError("session_revoked", "The session has been revoked")
        return claims

    def revoke_session(self, token: str) -> None:
        claims = self._decode(token, "session")
        self.replay_store.consume(claims["jti"], claims["exp"])

    def issue_ws_token(self, session_token: str, *, ttl: timedelta) -> str:
        session = self.verify_session(session_token)
        now = int(time.time())
        return self._encode({"kind": "ws", "sub": session["sub"], "org_id": session["org_id"], "roles": session["roles"], "iat": now, "exp": min(session["exp"], now + int(ttl.total_seconds())), "jti": str(uuid.uuid4())})

    def consume_ws_token(self, token: str) -> dict:
        claims = self._decode(token, "ws")
        if not self.replay_store.consume(claims["jti"], claims["exp"]):
            raise AuthError("token_replayed", "This WebSocket token has already been used")
        return claims
