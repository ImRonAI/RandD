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
