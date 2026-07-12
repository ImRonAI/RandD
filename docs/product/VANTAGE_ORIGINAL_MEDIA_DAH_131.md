# Vantage Original Media Verification (DAH-131)

DAH-131 moves original media verification behind a server-owned boundary:

- clients request an upload capability with expected filename, MIME type, byte size, and SHA-256;
- the server chooses the S3 bucket/key and stores a pending `original_upload`;
- clients cannot mark a `photo` verified or supply final object facts;
- the finalizer HEADs the actual S3 object with checksum mode enabled, verifies the requested version ID, checksum, size, MIME type, SSE-KMS key, Object Lock mode, and future retention, then persists the trusted facts in one repository transaction;
- signed reads are only issued for verified originals.

Runtime configuration lives in `backend/.env.example` under the `VANTAGE_S3_*` keys. The bucket must be created with S3 Object Lock enabled at bucket creation time, versioning enabled, public access blocked, and SSE-KMS available.

## Live AWS Acceptance Evidence

The configured AWS account `285527663773` now has a dedicated DAH-131 staging bucket:

- bucket: `vantage-originals-285527663773-us-east-1`
- region: `us-east-1`
- KMS alias: `alias/vantage-dah131-originals`
- Object Lock default retention: `COMPLIANCE`, 1 day
- versioning: enabled
- public access: blocked

Live acceptance command:

```bash
set -a
source /Users/tims-stuff/RandD/RandD/.env
set +a
KEY_ID=$(aws kms describe-key --key-id alias/vantage-dah131-originals --query KeyMetadata.Arn --output text)
AWS_ACCOUNT_ID=285527663773 \
VANTAGE_S3_BUCKET=vantage-originals-285527663773-us-east-1 \
VANTAGE_S3_REGION=us-east-1 \
VANTAGE_S3_KMS_KEY_ID="$KEY_ID" \
VANTAGE_S3_EXPECTED_BUCKET_OWNER=285527663773 \
VANTAGE_S3_RETENTION_DAYS=1 \
PYTHONPATH=/Users/tims-stuff/RandD/RandD-DAH-131/backend \
python3 /Users/tims-stuff/RandD/RandD-DAH-131/backend/scripts/verify_s3_originals_live.py --json
```

Observed result on 2026-07-12:

```json
{
  "bucket": "vantage-originals-285527663773-us-east-1",
  "checksumVerified": true,
  "failureRecorded": true,
  "kmsKeyId": "arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50",
  "objectKey": "00000000-0000-4000-8000-5220a7ba2e3e/00000000-0000-4000-8003-5220a7ba2e3e/originals/29f6d25b-744f-4e72-975c-a1ab5615ad4a.jpg",
  "objectLockMode": "COMPLIANCE",
  "photoStatus": "verified",
  "region": "us-east-1",
  "retentionUntil": "2026-07-13T13:20:54+00:00",
  "status": "verified",
  "versionId": "blgqPG_Kv09Adx_M_ahjLIACvxeb9O9r"
}
```
