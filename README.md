# RandD

Phase 1 STR QC kickoff artifacts:

- Schema: `/home/runner/work/RandD/RandD/sql/phase1_schema.sql`
- Architecture diagrams (ERD + state machine): `/home/runner/work/RandD/RandD/docs/phase1_architecture.md`
- Migration script: `/home/runner/work/RandD/RandD/scripts/migrate_phase1.py`

## Migration usage

```bash
python /home/runner/work/RandD/RandD/scripts/migrate_phase1.py \
  --master-csv /absolute/path/master.csv \
  --roster-csv /absolute/path/roster.csv \
  --db-path /absolute/path/str_qc.sqlite \
  --fail-on-error
```

Notes:
- The migration enables `PRAGMA foreign_keys=ON` on its connection and the schema also declares it.
- Plaintext secrets found in CSV inputs (for example WiFi password/door code) are surfaced as migration issues and are not stored as raw values.
