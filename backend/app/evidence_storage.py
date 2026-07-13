"""Immutable-original evidence storage with separate derivative objects."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ALLOWED_ORIGINAL_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/heif"})
MAX_ORIGINAL_BYTES = 50 * 1024 * 1024


class EvidenceValidationError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _safe(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"unsafe {field}")
    return value


@dataclass(frozen=True)
class EvidenceContext:
    org_id: str
    home_id: str
    inspection_id: str
    asset_id: str | None
    uploader_id: str


@dataclass(frozen=True)
class StoredMedia:
    media_id: str
    object_key: str
    sha256: str
    size: int
    mime_type: str
    original_id: str | None = None
    upload_status: str = "verified"


def verify_original(*, data: bytes, mime_type: str, expected_size: int | None = None,
                    expected_sha256: str | None = None) -> tuple[int, str]:
    """Validate an uploaded original before it can satisfy asset completeness."""
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime not in ALLOWED_ORIGINAL_MIME_TYPES:
        raise EvidenceValidationError("unsupported_media_type", "Unsupported original image MIME type")
    size = len(data)
    if size < 1 or size > MAX_ORIGINAL_BYTES:
        raise EvidenceValidationError("invalid_media_size", "Original image size is outside allowed limits")
    if expected_size is not None and expected_size != size:
        raise EvidenceValidationError("media_size_mismatch", "Uploaded object size does not match declaration",
                                      retryable=True)
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and not __import__("hmac").compare_digest(
        expected_sha256.lower(), digest
    ):
        raise EvidenceValidationError("media_hash_mismatch", "Uploaded object hash does not match declaration",
                                      retryable=True)
    return size, digest


class EvidenceStorage(Protocol):
    def put_original(self, context: EvidenceContext, filename: str, data: bytes,
                     mime_type: str) -> StoredMedia: ...
    def put_derivative(self, original: StoredMedia, kind: str, data: bytes,
                       mime_type: str) -> StoredMedia: ...


class LocalEvidenceStorage:
    """Local development/test backend preserving the same tenant-safe key shape."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _write(self, key: str, data: bytes) -> None:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("object key escapes storage root")
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
            stream.write(data)

    def put_original(self, context: EvidenceContext, filename: str, data: bytes,
                     mime_type: str) -> StoredMedia:
        org = _safe(context.org_id, "org_id")
        home = _safe(context.home_id, "home_id")
        size, digest = verify_original(data=data, mime_type=mime_type)
        media_id = str(uuid.uuid4())
        extension = Path(filename).suffix or mimetypes.guess_extension(mime_type) or ".bin"
        key = f"{org}/{home}/originals/{media_id}{extension}"
        self._write(key, data)
        return StoredMedia(media_id, key, digest, size, mime_type)

    def put_derivative(self, original: StoredMedia, kind: str, data: bytes,
                       mime_type: str) -> StoredMedia:
        _safe(kind, "derivative kind")
        parts = original.object_key.split("/")
        if len(parts) < 4 or parts[2] != "originals":
            raise ValueError("invalid original object key")
        media_id = str(uuid.uuid4())
        extension = mimetypes.guess_extension(mime_type) or ".bin"
        key = f"{parts[0]}/{parts[1]}/derivatives/{original.media_id}/{kind}-{media_id}{extension}"
        self._write(key, data)
        return StoredMedia(media_id, key, hashlib.sha256(data).hexdigest(), len(data), mime_type,
                           original.media_id)

    def read(self, media: StoredMedia) -> bytes:
        return (self.root / media.object_key).read_bytes()


class S3EvidenceStorage:
    """Production adapter requiring an Object-Lock-enabled bucket and retention."""

    def __init__(self, *, bucket: str, client: object, retention_days: int = 2557,
                 object_lock_enabled: bool = True) -> None:
        if not bucket or not object_lock_enabled:
            raise RuntimeError("S3 Object Lock bucket configuration is required")
        if retention_days < 1:
            raise RuntimeError("S3 Object Lock retention must be positive")
        self.bucket = bucket
        self.client = client
        self.retention_days = retention_days

    def put_original(self, context: EvidenceContext, filename: str, data: bytes,
                     mime_type: str) -> StoredMedia:
        from datetime import datetime, timedelta, timezone
        org, home = _safe(context.org_id, "org_id"), _safe(context.home_id, "home_id")
        media_id = str(uuid.uuid4())
        extension = Path(filename).suffix or mimetypes.guess_extension(mime_type) or ".bin"
        key = f"{org}/{home}/originals/{media_id}{extension}"
        size, sha256 = verify_original(data=data, mime_type=mime_type)
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=mime_type,
            ChecksumSHA256=__import__("base64").b64encode(bytes.fromhex(sha256)).decode(),
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=datetime.now(timezone.utc) + timedelta(days=self.retention_days),
            Metadata={"sha256": sha256, "inspection-id": context.inspection_id,
                      "uploader-id": context.uploader_id, "asset-id": context.asset_id or ""},
        )
        return StoredMedia(media_id, key, sha256, size, mime_type)

    def put_derivative(self, original: StoredMedia, kind: str, data: bytes,
                       mime_type: str) -> StoredMedia:
        _safe(kind, "derivative kind")
        org, home = original.object_key.split("/")[:2]
        media_id = str(uuid.uuid4())
        extension = mimetypes.guess_extension(mime_type) or ".bin"
        key = f"{org}/{home}/derivatives/{original.media_id}/{kind}-{media_id}{extension}"
        sha256 = hashlib.sha256(data).hexdigest()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime_type,
                               Metadata={"sha256": sha256, "original-id": original.media_id})
        return StoredMedia(media_id, key, sha256, len(data), mime_type, original.media_id)
