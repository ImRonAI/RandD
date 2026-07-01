#!/usr/bin/env python3
"""Load Master checklist and address roster CSV exports into the Phase 1 schema."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


TASK_STAGE_COLUMNS = {
    "QC": ["qc"],
    "B2B": ["b2b"],
    "CLN": ["cln", "clean", "cleaned"],
    "DONE": ["done"],
    "OWN": ["own", "owner"],
    "WO": ["wo", "workorder", "work_order"],
    "DONE_WO": ["donewo", "done_wo", "done(workorder)", "done(work_order)"],
    "REPORT": ["report"],
}

CHECKLIST_CATEGORY_ORDER = [
    "Hot Tub",
    "Housekeeping/Kitchen",
    "Housekeeping/Bathrooms",
    "Housekeeping/Bedroom",
    "Housekeeping/Home",
    "Outdoors",
    "Utilities",
    "Gifts",
]


@dataclass
class Issue:
    issue_type: str
    severity: str
    source_name: str
    row_number: Optional[int]
    property_code: Optional[str]
    message: str
    raw_payload: Dict[str, str]


class Migrator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.issues: List[Issue] = []

    def warn(self, issue_type: str, source_name: str, row_number: Optional[int], property_code: Optional[str], message: str, raw_payload: Dict[str, str]) -> None:
        self.issues.append(Issue(issue_type, "WARN", source_name, row_number, property_code, message, raw_payload))

    def error(self, issue_type: str, source_name: str, row_number: Optional[int], property_code: Optional[str], message: str, raw_payload: Dict[str, str]) -> None:
        self.issues.append(Issue(issue_type, "ERROR", source_name, row_number, property_code, message, raw_payload))

    @staticmethod
    def normalize_header(name: str) -> str:
        return "".join(ch for ch in name.lower().strip() if ch.isalnum())

    def get_field(self, row: Dict[str, str], aliases: Iterable[str]) -> str:
        normalized = {self.normalize_header(k): (v or "").strip() for k, v in row.items()}
        for alias in aliases:
            key = self.normalize_header(alias)
            if key in normalized:
                return normalized[key]
        return ""

    def parse_bool(self, value: str, *, source_name: str, row_number: int, property_code: Optional[str], column_name: str, raw_row: Dict[str, str]) -> Optional[bool]:
        lowered = (value or "").strip().lower()
        if lowered in {"true", "t", "yes", "y", "1", "x"}:
            return True
        if lowered in {"false", "f", "no", "n", "0"}:
            return False
        if lowered == "":
            self.warn("blank_status", source_name, row_number, property_code, f"Blank status in column '{column_name}'.", raw_row)
            return None
        self.error("invalid_status", source_name, row_number, property_code, f"Unrecognized status '{value}' in column '{column_name}'.", raw_row)
        return None

    def parse_date(self, value: str, *, source_name: str, row_number: int, property_code: Optional[str], raw_row: Dict[str, str]) -> Optional[str]:
        text = (value or "").strip()
        if not text:
            self.warn("blank_arrival_date", source_name, row_number, property_code, "Blank arrival date.", raw_row)
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        self.error("invalid_arrival_date", source_name, row_number, property_code, f"Unparseable arrival date '{value}'.", raw_row)
        return None

    def ensure_property(self, code: str, source_name: str, row_number: int, address: str, raw_row: Dict[str, str]) -> int:
        code = code.strip().upper()
        cur = self.conn.execute("SELECT property_id, address_line_1 FROM property WHERE unit_code = ?", (code,))
        existing = cur.fetchone()
        if existing:
            prop_id, existing_address = existing
            if address and existing_address and existing_address.strip() != address.strip():
                self.error(
                    "duplicate_code_conflicting_address",
                    source_name,
                    row_number,
                    code,
                    f"Property code '{code}' has conflicting addresses: '{existing_address}' vs '{address}'. Keeping existing address.",
                    raw_row,
                )
            return prop_id
        self.conn.execute(
            """
            INSERT INTO property (unit_code, address_line_1, roster_active)
            VALUES (?, ?, 1)
            """,
            (code, address or None),
        )
        return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def seed_template(self) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO checklist_template (template_name, version_label) VALUES (?, ?)",
            ("Master Checklist", "v1"),
        )
        template_id = self.conn.execute(
            "SELECT checklist_template_id FROM checklist_template WHERE template_name = ? AND version_label = ?",
            ("Master Checklist", "v1"),
        ).fetchone()[0]
        for idx, category in enumerate(CHECKLIST_CATEGORY_ORDER, start=1):
            self.conn.execute(
                "INSERT OR IGNORE INTO checklist_category (checklist_template_id, category_name, display_order) VALUES (?, ?, ?)",
                (template_id, category, idx),
            )

    def ingest_roster(self, roster_csv: Path) -> Dict[str, int]:
        property_ids: Dict[str, int] = {}
        with roster_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_number, row in enumerate(reader, start=2):
                code = self.get_field(row, ["Property", "House", "Code", "Unit", "Unit Code"])
                if not code:
                    self.error("missing_property_code", "address_roster", row_number, None, "Missing property code in address roster row.", row)
                    continue
                code = code.strip().upper()
                address = self.get_field(row, ["Address", "Address 1", "Street"])
                cluster = self.get_field(row, ["Cluster", "Neighborhood", "Geo Cluster", "Area"])
                display_name = self.get_field(row, ["Display Name", "Property Name", "Name"])
                wifi_raw = self.get_field(row, ["WiFi", "Wifi", "Wi-Fi"])
                wifi_ssid = self.get_field(row, ["WiFi SSID", "SSID"])
                wifi_password = self.get_field(row, ["WiFi Password", "Password", "Passcode"])
                if wifi_raw and "/." in wifi_raw and (not wifi_ssid and not wifi_password):
                    wifi_ssid, wifi_password = [part.strip() for part in wifi_raw.split("/.", 1)]

                prop_id = self.ensure_property(code, "address_roster", row_number, address, row)
                property_ids[code] = prop_id

                if cluster:
                    self.conn.execute("INSERT OR IGNORE INTO cluster (name) VALUES (?)", (cluster,))
                    cluster_id = self.conn.execute("SELECT cluster_id FROM cluster WHERE name = ?", (cluster,)).fetchone()[0]
                else:
                    cluster_id = None

                self.conn.execute(
                    """
                    UPDATE property
                    SET display_name = COALESCE(NULLIF(?, ''), display_name),
                        address_line_1 = COALESCE(NULLIF(?, ''), address_line_1),
                        wifi_ssid = COALESCE(NULLIF(?, ''), wifi_ssid),
                        wifi_password = COALESCE(NULLIF(?, ''), wifi_password),
                        wifi_raw = COALESCE(NULLIF(?, ''), wifi_raw),
                        cluster_id = COALESCE(?, cluster_id),
                        updated_at = datetime('now')
                    WHERE property_id = ?
                    """,
                    (display_name, address, wifi_ssid, wifi_password, wifi_raw, cluster_id, prop_id),
                )

        return property_ids

    def ingest_master(self, master_csv: Path, roster_property_ids: Dict[str, int]) -> Dict[str, int]:
        task_counts: Dict[str, int] = {}
        with master_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_number, row in enumerate(reader, start=2):
                code = self.get_field(row, ["House", "Property", "Unit", "Code", "Unit Code"])
                if not code:
                    self.error("missing_property_code", "master_checklist", row_number, None, "Missing property code in master checklist row.", row)
                    continue
                code = code.strip().upper()
                property_id = roster_property_ids.get(code)
                if property_id is None:
                    self.warn("task_property_missing_in_roster", "master_checklist", row_number, code, "Property exists in task list but not in address roster. Creating stub property.", row)
                    property_id = self.ensure_property(code, "master_checklist", row_number, "", row)
                    roster_property_ids[code] = property_id

                arrival_raw = self.get_field(row, ["Arrival", "Arrival Date", "Date"])
                arrival_date = self.parse_date(arrival_raw, source_name="master_checklist", row_number=row_number, property_code=code, raw_row=row)
                housekeeper = self.get_field(row, ["Cleaner", "Housekeeper", "Assigned Housekeeper"])

                self.conn.execute(
                    """
                    INSERT INTO task (property_id, arrival_date, assigned_housekeeper_name, current_stage, source_row_number, source_system)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (property_id, arrival_date, housekeeper or None, None, row_number, "master_checklist_csv"),
                )
                task_id = int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

                latest_stage: Optional[str] = None
                for stage_key, aliases in TASK_STAGE_COLUMNS.items():
                    raw_value = self.get_field(row, aliases)
                    parsed = self.parse_bool(
                        raw_value,
                        source_name="master_checklist",
                        row_number=row_number,
                        property_code=code,
                        column_name=aliases[0],
                        raw_row=row,
                    )
                    if parsed is None:
                        continue
                    self.conn.execute(
                        """
                        INSERT INTO task_stage_event (task_id, stage_key, is_complete, completed_at, source_value)
                        VALUES (?, ?, ?, CASE WHEN ? = 1 THEN datetime('now') ELSE NULL END, ?)
                        """,
                        (task_id, stage_key, 1 if parsed else 0, 1 if parsed else 0, raw_value),
                    )
                    if parsed:
                        latest_stage = stage_key

                self.conn.execute("UPDATE task SET current_stage = ? WHERE task_id = ?", (latest_stage, task_id))
                task_counts[code] = task_counts.get(code, 0) + 1

        return task_counts

    def flag_roster_only_properties(self, roster_property_ids: Dict[str, int], task_counts: Dict[str, int]) -> None:
        for code in sorted(roster_property_ids.keys()):
            if code not in task_counts:
                self.warn(
                    "roster_property_without_active_task",
                    "cross_check",
                    None,
                    code,
                    "Property exists in address roster but has no active task in checklist import.",
                    {},
                )

    def persist_issues(self) -> None:
        for issue in self.issues:
            self.conn.execute(
                """
                INSERT INTO migration_issue (issue_type, severity, source_name, row_number, property_code, message, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue.issue_type,
                    issue.severity,
                    issue.source_name,
                    issue.row_number,
                    issue.property_code,
                    issue.message,
                    json.dumps(issue.raw_payload, ensure_ascii=False),
                ),
            )


def create_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def run(master_csv: Path, roster_csv: Path, db_path: Path, schema_path: Path, fail_on_error: bool) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        create_schema(conn, schema_path)
        migrator = Migrator(conn)
        migrator.seed_template()
        roster = migrator.ingest_roster(roster_csv)
        task_counts = migrator.ingest_master(master_csv, roster)
        migrator.flag_roster_only_properties(roster, task_counts)
        migrator.persist_issues()
        conn.commit()

        error_count = sum(1 for issue in migrator.issues if issue.severity == "ERROR")
        warn_count = sum(1 for issue in migrator.issues if issue.severity == "WARN")
        print(f"Migration completed: {len(roster)} properties, {sum(task_counts.values())} tasks.")
        print(f"Data quality issues: {error_count} errors, {warn_count} warnings.")
        for issue in migrator.issues:
            row_part = f" row={issue.row_number}" if issue.row_number else ""
            code_part = f" property={issue.property_code}" if issue.property_code else ""
            print(f"[{issue.severity}] {issue.issue_type}{row_part}{code_part}: {issue.message}")

        if fail_on_error and error_count:
            return 2
        return 0
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master-csv", required=True, type=Path, help="Path to exported Master checklist CSV")
    parser.add_argument("--roster-csv", required=True, type=Path, help="Path to exported address roster CSV")
    parser.add_argument("--db-path", required=True, type=Path, help="SQLite database output path")
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "sql" / "phase1_schema.sql",
        help="Path to SQL schema file",
    )
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero if any ERROR issues are detected")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(args.master_csv, args.roster_csv, args.db_path, args.schema_path, args.fail_on_error)


if __name__ == "__main__":
    raise SystemExit(main())
