# DAH-124 Vantage schema freeze

This is the handoff contract for DAH-125, DAH-126, DAH-127, and DAH-131. Migration `0001` remains unchanged; `0002` is the forward reconciliation.

- 0001_sha256: `12c08d6cf03d49c0801155e3dfbe9adc7a3ae36d974270f793f4a7e3ac75cdaf`
- 0002_sha256: `bb3ab3b6a2dd219602f470aa1a2c11bc4bb8273d0e7205e1dbd98a7792f40853`

## Frozen mapping

| Concern | FastAPI/domain | SQLite | PostgreSQL after 0002 |
|---|---|---|---|
| inspection discriminator | request field `type`; repository field `inspection_type` | `inspection.inspection_type` | `inspection.inspection_type` / enum `inspection_type` |
| inspection values | `onboarding`, `turnover` | CHECK | enum |
| client replay identity | non-empty opaque text | text | text after forward cast from the foundation UUID columns |
| photo purpose | server-created asset upload is explicitly `asset_original` | constrained text, default `asset_original` | `photo_purpose`, default `asset_original` |
| original key | `{organization_id}/{home_id}/originals/{media_id}.{extension}` | exact org/home prefix and server UUID verified | same key stored in `photo.original_object_key` |
| result | `PASS`, `FAIL`, `NA` | constrained `inspection_item_result.result` | `inspection_result` enum |
| result history | append revision with `version` and `supersedes_result_id` | composite same-item FK | composite same-item FK |
| result evidence | zero or more ordered originals | `result_photo` | `result_photo` |

The server supplies `organization_id`, `home_id`, `inspection_id`, generated `photo_id`, and the evidence-storage `media_id`. Clients cannot choose an alternate tenant/home key prefix or non-UUID original name. A scoped `client_id` replay is accepted only when its payload matches the original write; otherwise the domain returns `idempotency_payload_conflict`.

## Checklist identity

`checklist_item` contains exactly the 38 current `app.qc_journal.CHECKLIST_ITEMS` labels. `item_key` is the stable storage/API identity; `section_name` and `label` preserve exact presentation text. Repeated recordings append result revisions and never overwrite history. Any number of verified originals may be linked, with unique display order per result.

## Composite ownership

Room-to-inspection, asset-to-room/inspection, photo-to-room/asset/inspection, result-to-inspection, result-photo, inspection-to-inventory provenance, and evidence-approval relationships carry organization and home identifiers in their foreign keys. Result-photo and approval links also carry inspection identity; item approvals carry the exact immutable result revision ID. A nullable asset on `photo` requires a non-null room when present, preventing nullable-composite-FK bypass.

## Historical House Keeping compatibility

Legacy reports remain raw, readable records after they have an explicit organization assignment. Compatibility maps `state.items[].id` to the frozen checklist key because historical labels may contain photo/note decorations. Historical `checked` is exposed only as a boolean; it is never converted to PASS, FAIL, or NA. No Room inventory is inferred from historical reports. The forward PostgreSQL table has a composite organization/report key and FORCE RLS; DAH-127 owns assignment during ingestion and must quarantine ambiguous or blank-property rows rather than guessing.

The checked-in read-only audit (`backend/scripts/audit_legacy_housekeeping.py str_qc.sqlite`) proves the current source contains 51 reports, 38 distinct item IDs, and 215 photos with at most three photos per item, with zero unknown IDs. These counts are an intentional drift gate.

## Verification boundary

The `canonical-schema` CI job runs the DAH-124 drift test, verifies both migration checksums and the exact 38-item Python/SQLite catalog, and parses every PostgreSQL migration with `pglast`. A real PostgreSQL execution was not available in this checkout because the local Docker daemon was not running; executable migration/RLS qualification remains a DAH-128 gate.
