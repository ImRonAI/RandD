"""Live DAH-131 S3 originals acceptance.

This script uses real AWS credentials from the standard environment. It creates
one short-lived original object through the same storage adapter used by the
FastAPI runtime, then verifies that S3 returns immutable version, checksum,
SSE-KMS, and Object Lock retention facts before the repository marks the upload
verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import boto3

os.environ.setdefault("VANTAGE_SKIP_SLACK_REFRESH", "1")

from app.vantage.domain import DomainError, VantageRepository
from app.vantage.media_finalizer import OriginalMediaService, S3OriginalObjectStore
from app.vantage.schema import install_sqlite_schema


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _bootstrap(repository: VantageRepository, nonce: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    organization_id = f"00000000-0000-4000-8000-{nonce[:12]}"
    portfolio_id = f"00000000-0000-4000-8001-{nonce[:12]}"
    user_id = f"00000000-0000-4000-8002-{nonce[:12]}"
    home_id = f"00000000-0000-4000-8003-{nonce[:12]}"
    repository.bootstrap_organization(organization_id, "DAH-131 Live", portfolio_id)
    repository.bootstrap_user(user_id, f"dah131-{nonce}@example.invalid", organization_id, "INSPECTOR")
    repository.create_home(organization_id, portfolio_id, home_id, "Live S3 Evidence Home")
    inspection = repository.start_inspection(organization_id, user_id, home_id, "onboarding", f"inspection-{nonce}")
    room = repository.create_room(
        organization_id,
        user_id,
        home_id,
        inspection["id"],
        repository.list_room_types(organization_id)[0]["id"],
        "Kitchen",
        f"room-{nonce}",
    )
    asset = repository.create_asset(
        organization_id,
        user_id,
        room["id"],
        inspection["id"],
        "Appliance",
        "Refrigerator",
        f"asset-{nonce}",
    )
    return inspection, room, asset


def run() -> dict[str, Any]:
    bucket = _require_env("VANTAGE_S3_BUCKET")
    kms_key_id = _require_env("VANTAGE_S3_KMS_KEY_ID")
    expected_owner = os.getenv("VANTAGE_S3_EXPECTED_BUCKET_OWNER", "").strip() or _require_env("AWS_ACCOUNT_ID")
    region = os.getenv("VANTAGE_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    retention_days = int(os.getenv("VANTAGE_S3_RETENTION_DAYS", "1"))
    nonce = uuid.uuid4().hex
    data = f"DAH-131 live original evidence {nonce}\n".encode()
    sha256 = hashlib.sha256(data).hexdigest()

    s3 = boto3.client("s3", region_name=region)
    storage = S3OriginalObjectStore(
        client=s3,
        bucket=bucket,
        kms_key_id=kms_key_id,
        expected_bucket_owner=expected_owner,
        retention_days=retention_days,
    )
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "dah131-live.sqlite"

        def connect() -> sqlite3.Connection:
            connection = sqlite3.connect(db)
            connection.execute("PRAGMA foreign_keys=ON")
            return connection

        with connect() as connection:
            install_sqlite_schema(connection)
        repository = VantageRepository(connect)
        service = OriginalMediaService(repository, storage, read_expires_seconds=60)
        inspection, room, asset = _bootstrap(repository, nonce)
        upload = service.initiate(
            inspection["organization_id"],
            "00000000-0000-4000-8002-" + nonce[:12],
            home_id=room["home_id"],
            room_id=room["id"],
            asset_id=asset["id"],
            inspection_id=inspection["id"],
            client_id=f"upload-{nonce}",
            filename="original.jpg",
            mime_type="image/jpeg",
            byte_size=len(data),
            sha256=sha256,
        )
        target = upload["target"]
        if target["method"] != "PUT":
            raise RuntimeError("upload target must be a presigned PUT")
        request = Request(
            target["url"],
            data=data,
            method="PUT",
            headers=target["requiredHeaders"],
        )
        with urlopen(request, timeout=30) as response:
            version_id = response.headers.get("x-amz-version-id", "")
        if not version_id:
            raise RuntimeError("presigned PUT did not return an immutable version ID")
        head = s3.head_object(
            Bucket=bucket,
            Key=upload["objectKey"],
            VersionId=version_id,
            ChecksumMode="ENABLED",
            ExpectedBucketOwner=expected_owner,
        )
        if str(head.get("VersionId") or "") != version_id:
            raise RuntimeError("HeadObject version did not match the uploaded version")
        result = service.finalize(inspection["organization_id"], upload["uploadId"], version_id)
        stored = repository.get_original_upload(inspection["organization_id"], upload["uploadId"])
        missing = service.initiate(
            inspection["organization_id"],
            "00000000-0000-4000-8002-" + nonce[:12],
            home_id=room["home_id"],
            room_id=room["id"],
            asset_id=asset["id"],
            inspection_id=inspection["id"],
            client_id=f"missing-{nonce}",
            filename="missing.jpg",
            mime_type="image/jpeg",
            byte_size=len(data),
            sha256=sha256,
        )
        try:
            service.finalize(inspection["organization_id"], missing["uploadId"], "missing-version")
            raise RuntimeError("missing S3 original finalized unexpectedly")
        except DomainError as exc:
            if exc.code != "storage_inspection_failed" or not exc.retryable:
                raise
        failed = repository.get_original_upload(inspection["organization_id"], missing["uploadId"])
        failure_recorded = (
            failed["status"] == "failed"
            and failed["photo_status"] == "failed"
            and failed["last_error_code"] == "storage_inspection_failed"
            and failed["verification_attempts"] == 1
        )
        return {
            "bucket": bucket,
            "region": region,
            "objectKey": upload["objectKey"],
            "versionId": version_id,
            "checksumVerified": result["sha256"] == sha256,
            "failureRecorded": failure_recorded,
            "status": result["status"],
            "photoStatus": stored["photo_status"],
            "kmsKeyId": stored["kms_key_id"],
            "objectLockMode": stored["object_lock_mode"],
            "retentionUntil": stored["retention_until"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    evidence = run()
    print(json.dumps(evidence, indent=2 if args.json else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DAH-131 live S3 verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
