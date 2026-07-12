"""Server-owned original upload and immutable storage verification boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from .domain import DomainError


@dataclass(frozen=True)
class ObjectFacts:
    storage_bucket: str
    object_key: str
    storage_version_id: str
    byte_size: int
    mime_type: str
    sha256: str | None
    etag: str | None
    encryption_algorithm: str | None
    kms_key_id: str | None
    object_lock_mode: str | None
    retention_until: datetime | None
    legal_hold_status: str | None


class OriginalObjectStore(Protocol):
    bucket: str

    def create_upload_target(self, *, object_key: str, mime_type: str, byte_size: int,
                             sha256: str) -> dict[str, Any]: ...
    def inspect(self, *, object_key: str, version_id: str | None = None) -> ObjectFacts: ...
    def read_bytes(self, *, object_key: str, version_id: str) -> bytes: ...
    def create_read_url(self, *, object_key: str, version_id: str, expires_seconds: int) -> str: ...


class S3OriginalObjectStore:
    """Private S3 Object-Lock store; ETag is never treated as a content hash."""

    def __init__(self, *, client: Any, bucket: str, kms_key_id: str,
                 expected_bucket_owner: str, retention_days: int = 2557) -> None:
        if not all((bucket, kms_key_id, expected_bucket_owner)) or retention_days < 1:
            raise RuntimeError("S3 bucket, KMS key, owner, and positive retention are required")
        self.client, self.bucket, self.kms_key_id = client, bucket, kms_key_id
        self.expected_bucket_owner, self.retention_days = expected_bucket_owner, retention_days

    def create_upload_target(self, *, object_key: str, mime_type: str, byte_size: int,
                             sha256: str) -> dict[str, Any]:
        checksum = base64.b64encode(bytes.fromhex(sha256)).decode()
        retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
        params = {
            "Bucket": self.bucket, "Key": object_key, "ContentType": mime_type,
            "ChecksumSHA256": checksum, "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": self.kms_key_id, "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": retain_until,
            "ExpectedBucketOwner": self.expected_bucket_owner,
        }
        return {
            "method": "PUT",
            "url": self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=900),
            "expiresIn": 900,
            "requiredHeaders": {
                "content-type": mime_type, "x-amz-checksum-sha256": checksum,
                "x-amz-server-side-encryption": "aws:kms",
                "x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id,
                "x-amz-object-lock-mode": "COMPLIANCE",
                "x-amz-object-lock-retain-until-date": retain_until.isoformat(),
            },
            "maxBytes": byte_size,
        }

    def inspect(self, *, object_key: str, version_id: str | None = None) -> ObjectFacts:
        params: dict[str, Any] = {
            "Bucket": self.bucket, "Key": object_key, "ChecksumMode": "ENABLED",
            "ExpectedBucketOwner": self.expected_bucket_owner,
        }
        if version_id:
            params["VersionId"] = version_id
        head = self.client.head_object(**params)
        checksum = head.get("ChecksumSHA256")
        sha256 = base64.b64decode(checksum).hex() if checksum else None
        return ObjectFacts(
            self.bucket, object_key, str(head.get("VersionId") or ""), int(head["ContentLength"]),
            str(head.get("ContentType") or "").split(";", 1)[0].lower(), sha256,
            str(head.get("ETag") or "").strip('"') or None, head.get("ServerSideEncryption"),
            head.get("SSEKMSKeyId"), head.get("ObjectLockMode"), head.get("ObjectLockRetainUntilDate"),
            head.get("ObjectLockLegalHoldStatus"),
        )

    def read_bytes(self, *, object_key: str, version_id: str) -> bytes:
        response = self.client.get_object(
            Bucket=self.bucket, Key=object_key, VersionId=version_id,
            ExpectedBucketOwner=self.expected_bucket_owner,
        )
        return response["Body"].read()

    def create_read_url(self, *, object_key: str, version_id: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key, "VersionId": version_id,
                    "ExpectedBucketOwner": self.expected_bucket_owner},
            ExpiresIn=expires_seconds,
        )


class OriginalMediaService:
    def __init__(
        self,
        repository: Any,
        storage: OriginalObjectStore,
        *,
        read_expires_seconds: int = 300,
    ) -> None:
        if read_expires_seconds < 1 or read_expires_seconds > 3600:
            raise RuntimeError("Signed original read URLs must expire within 1 hour")
        self.repository, self.storage = repository, storage
        self.read_expires_seconds = read_expires_seconds

    @contextmanager
    def _active_repo(self, organization_id: str, user_id: str | None, read_only: bool = False) -> Iterator[Any]:
        tx_attr = "read_only_transaction" if read_only else "transaction"
        transaction = getattr(self.repository, tx_attr, None)
        if transaction is None:
            yield self.repository
        else:
            if not user_id:
                raise DomainError("user_id_required", "user_id is required for transaction context")
            from .context import TenantContext
            context = TenantContext(user_id, organization_id, frozenset({"SYSTEM_JOB"}))
            with transaction(context) as active:
                yield active

    def initiate(self, organization_id: str, user_id: str, **request: Any) -> dict[str, Any]:
        with self._active_repo(organization_id, user_id) as active:
            upload = active.initiate_original_upload(
                organization_id, user_id, storage_bucket=self.storage.bucket, **request,
            )
        target = self.storage.create_upload_target(
            object_key=upload["object_key"], mime_type=upload["expected_mime_type"],
            byte_size=upload["expected_byte_size"], sha256=upload["expected_sha256"],
        )
        return {"uploadId": upload["upload_id"], "photoId": upload["photo_id"],
                "objectKey": upload["object_key"], "status": upload["status"], "target": target}

    def finalize(self, organization_id: str, upload_id: str,
                 version_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        with self._active_repo(organization_id, user_id) as active:
            upload = active.get_original_upload(organization_id, upload_id)
            try:
                result, sha256 = self._finalize_checked(organization_id, upload_id, upload, version_id, active)
            except DomainError as error:
                active.record_original_upload_failure(organization_id, upload_id, error.code)
                raise
        return {
            "uploadId": upload_id,
            "photoId": result["photo_id"],
            "status": result["status"],
            "versionId": result["storage_version_id"],
            "sha256": sha256,
        }

    def _finalize_checked(
        self,
        organization_id: str,
        upload_id: str,
        upload: dict[str, Any],
        version_id: str | None,
        active: Any,
    ) -> tuple[dict[str, Any], str]:
        if not version_id:
            raise DomainError("storage_version_required", "The immutable S3 version ID is required")
        try:
            facts = self.storage.inspect(object_key=upload["object_key"], version_id=version_id)
        except Exception as exc:
            raise DomainError(
                "storage_inspection_failed",
                "Stored original facts could not be read",
                retryable=True,
            ) from exc
        if facts.storage_bucket != upload["storage_bucket"] or facts.object_key != upload["object_key"]:
            raise DomainError("storage_identity_mismatch", "Stored object does not match the upload capability")
        if not facts.storage_version_id:
            raise DomainError("storage_version_missing", "Stored original has no immutable version ID")
        if not hmac.compare_digest(facts.storage_version_id, version_id):
            raise DomainError("storage_version_mismatch", "Stored original version does not match")
        sha256 = facts.sha256
        if sha256 is None:
            try:
                original = self.storage.read_bytes(
                    object_key=facts.object_key, version_id=facts.storage_version_id,
                )
            except Exception as exc:
                raise DomainError(
                    "storage_read_failed",
                    "Stored original bytes could not be read for checksum verification",
                    retryable=True,
                ) from exc
            sha256 = hashlib.sha256(original).hexdigest()
        if not hmac.compare_digest(sha256, str(upload["expected_sha256"])):
            raise DomainError("media_hash_mismatch", "Stored object hash does not match", retryable=True)
        if facts.byte_size != upload["expected_byte_size"]:
            raise DomainError("media_size_mismatch", "Stored object size does not match", retryable=True)
        if facts.mime_type != upload["expected_mime_type"]:
            raise DomainError("media_type_mismatch", "Stored object MIME type does not match")
        expected_kms_key_id = getattr(self.storage, "kms_key_id", None)
        if facts.encryption_algorithm != "aws:kms" or not facts.kms_key_id:
            raise DomainError("storage_encryption_unverified", "SSE-KMS is required")
        if expected_kms_key_id and facts.kms_key_id != expected_kms_key_id:
            raise DomainError("storage_encryption_unverified", "SSE-KMS key does not match")
        if facts.object_lock_mode != "COMPLIANCE":
            raise DomainError("storage_retention_unverified", "Object Lock compliance retention is required")
        retention_until = self._utc_datetime(facts.retention_until)
        if not retention_until or retention_until <= datetime.now(timezone.utc):
            raise DomainError("storage_retention_unverified", "Object retention is missing or expired")
        result = active._finalize_original_from_storage(organization_id, upload_id, {
            "storage_bucket": facts.storage_bucket,
            "object_key": facts.object_key,
            "storage_version_id": facts.storage_version_id,
            "byte_size": facts.byte_size,
            "mime_type": facts.mime_type,
            "sha256": sha256,
            "etag": facts.etag,
            "encryption_algorithm": facts.encryption_algorithm,
            "kms_key_id": facts.kms_key_id,
            "object_lock_mode": facts.object_lock_mode,
            "retention_until": retention_until.isoformat(),
            "legal_hold_status": facts.legal_hold_status,
        })
        return result, sha256

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def signed_read(self, organization_id: str, upload_id: str, user_id: str | None = None) -> dict[str, Any]:
        with self._active_repo(organization_id, user_id, read_only=True) as active:
            upload = active.get_original_upload(organization_id, upload_id)
        if upload["status"] != "verified" or not upload["storage_version_id"]:
            raise DomainError("original_not_verified", "Original is not available")
        return {"url": self.storage.create_read_url(
                    object_key=upload["object_key"], version_id=upload["storage_version_id"],
                    expires_seconds=self.read_expires_seconds),
                "expiresIn": self.read_expires_seconds, "photoId": upload["photo_id"], "versionId": upload["storage_version_id"]}
