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

FEATURE_COLUMNS = {
    "HOT_TUB": ["hot tub", "has hot tub"],
    "TV": ["tv", "has tv", "tvs"],
    "EV_CHARGER": ["ev charger", "has ev charger"],
    "ARCADE_GAME": ["arcade", "arcade games", "game room"],
    "PATIO": ["patio", "patios"],
    "PORCH": ["porch", "porches"],
    "BATHROOM": ["bathroom", "bathrooms"],
    "BEDROOM": ["bedroom", "bedrooms"],
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
    property_id: Optional[int]
    message: str
    raw_payload: Dict[str, str]


class Migrator:
    def __init__(self, conn: sqlite3.Connection, tenant_id: int = 1):
        self.conn = conn
        # All tenant-owned INSERTs are stamped with this. Defaults to 1
        # (RandD Tradesmen) so the original CLI behavior is unchanged; the
        # onboarding API passes the target tenant's id.
        self.tenant_id = int(tenant_id)
        self.issues: List[Issue] = []
        self.stage_map = self._load_stage_map()
        self.role_map = self._load_role_map()

    def _load_stage_map(self) -> Dict[str, int]:
        rows = self.conn.execute("SELECT stage_key, stage_definition_id FROM stage_definition WHERE is_active = 1").fetchall()
        return {row[0]: int(row[1]) for row in rows}

    def _load_role_map(self) -> Dict[str, int]:
        rows = self.conn.execute("SELECT role_key, role_id FROM role").fetchall()
        return {row[0]: int(row[1]) for row in rows}

    def warn(
        self,
        issue_type: str,
        source_name: str,
        row_number: Optional[int],
        property_code: Optional[str],
        message: str,
        raw_payload: Dict[str, str],
        property_id: Optional[int] = None,
    ) -> None:
        self.issues.append(Issue(issue_type, "WARN", source_name, row_number, property_code, property_id, message, raw_payload))

    def error(
        self,
        issue_type: str,
        source_name: str,
        row_number: Optional[int],
        property_code: Optional[str],
        message: str,
        raw_payload: Dict[str, str],
        property_id: Optional[int] = None,
    ) -> None:
        self.issues.append(Issue(issue_type, "ERROR", source_name, row_number, property_code, property_id, message, raw_payload))

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

    def parse_bool(
        self,
        value: str,
        *,
        source_name: str,
        row_number: int,
        property_code: Optional[str],
        column_name: str,
        raw_row: Dict[str, str],
        property_id: Optional[int] = None,
    ) -> Optional[bool]:
        lowered = (value or "").strip().lower()
        if lowered in {"true", "t", "yes", "y", "1", "x"}:
            return True
        if lowered in {"false", "f", "no", "n", "0"}:
            return False
        if lowered == "":
            self.warn("blank_status", source_name, row_number, property_code, f"Blank status in column '{column_name}'.", raw_row, property_id=property_id)
            return None
        self.error("invalid_status", source_name, row_number, property_code, f"Unrecognized status '{value}' in column '{column_name}'.", raw_row, property_id=property_id)
        return None

    def parse_date(
        self,
        value: str,
        *,
        source_name: str,
        row_number: int,
        property_code: Optional[str],
        raw_row: Dict[str, str],
        property_id: Optional[int] = None,
    ) -> Optional[str]:
        text = (value or "").strip()
        if not text:
            self.warn("blank_arrival_date", source_name, row_number, property_code, "Blank arrival date.", raw_row, property_id=property_id)
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        self.error("invalid_arrival_date", source_name, row_number, property_code, f"Unparseable arrival date '{value}'.", raw_row, property_id=property_id)
        return None

    def parse_quantity(self, value: str) -> Optional[int]:
        text = (value or "").strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered in {"true", "t", "yes", "y", "x"}:
            return 1
        if lowered in {"false", "f", "no", "n", "0"}:
            return 0
        if text.isdigit():
            return int(text)
        return None

    def ensure_stakeholder(self, full_name: str) -> Optional[int]:
        name = (full_name or "").strip()
        if not name:
            return None
        row = self.conn.execute(
            "SELECT stakeholder_id FROM stakeholder WHERE full_name = ? AND tenant_id = ?",
            (name, self.tenant_id),
        ).fetchone()
        if row:
            return int(row[0])
        self.conn.execute(
            "INSERT INTO stakeholder (full_name, tenant_id) VALUES (?, ?)",
            (name, self.tenant_id),
        )
        return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def ensure_stakeholder_role(self, stakeholder_id: Optional[int], role_key: str, property_id: Optional[int] = None) -> None:
        if stakeholder_id is None:
            return
        role_id = self.role_map.get(role_key)
        if role_id is None:
            return
        self.conn.execute(
            """
            INSERT OR IGNORE INTO stakeholder_role (stakeholder_id, role_id, property_id, tenant_id)
            VALUES (?, ?, ?, ?)
            """,
            (stakeholder_id, role_id, property_id, self.tenant_id),
        )

    def ensure_property(self, code: str, source_name: str, row_number: int, address: str, raw_row: Dict[str, str]) -> int:
        code = code.strip().upper()
        cur = self.conn.execute(
            "SELECT property_id, address_line_1 FROM property WHERE unit_code = ? AND tenant_id = ?",
            (code, self.tenant_id),
        )
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
                    property_id=int(prop_id),
                )
            return int(prop_id)
        self.conn.execute(
            """
            INSERT INTO property (unit_code, address_line_1, roster_active, source_system, tenant_id)
            VALUES (?, ?, 1, ?, ?)
            """,
            (code, address or None, source_name, self.tenant_id),
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

    def upsert_property_feature(self, property_id: int, feature_key: str, quantity: int, notes: str = "") -> None:
        feature_row = self.conn.execute(
            "SELECT feature_type_id FROM property_feature_type WHERE feature_key = ?",
            (feature_key,),
        ).fetchone()
        if feature_row is None:
            return
        feature_type_id = int(feature_row[0])
        self.conn.execute(
            """
            INSERT INTO property_feature (property_id, feature_type_id, location_label, quantity, notes, last_verified_at)
            VALUES (?, ?, '', ?, NULLIF(?, ''), datetime('now'))
            ON CONFLICT(property_id, feature_type_id, location_label)
            DO UPDATE SET quantity = excluded.quantity,
                          notes = COALESCE(NULLIF(excluded.notes, ''), property_feature.notes),
                          last_verified_at = datetime('now')
            """,
            (property_id, feature_type_id, quantity, notes),
        )

    def handle_sensitive_credential(
        self,
        source_name: str,
        row_number: int,
        property_code: str,
        property_id: int,
        credential_name: str,
        raw_row: Dict[str, str],
    ) -> None:
        self.warn(
            "sensitive_plaintext_input",
            source_name,
            row_number,
            property_code,
            f"Detected plaintext {credential_name}; migrated without storing raw secret. Populate *_ciphertext or *_secret_ref in a secure follow-up step.",
            raw_row,
            property_id=property_id,
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
                standing_instructions = self.get_field(row, ["Standing Instructions", "Instructions", "Notes", "Quirks"])
                qc_assignee = self.get_field(row, ["QC Assignee", "QC", "Inspector"])

                wifi_raw = self.get_field(row, ["WiFi", "Wifi", "Wi-Fi"])
                wifi_ssid = self.get_field(row, ["WiFi SSID", "SSID"])
                wifi_password = self.get_field(row, ["WiFi Password", "Password", "Passcode"])
                if wifi_raw and "/." in wifi_raw and (not wifi_ssid and not wifi_password):
                    wifi_ssid, wifi_password = [part.strip() for part in wifi_raw.split("/.", 1)]

                door_code = self.get_field(row, ["Door Code", "Code", "Access Code"])

                prop_id = self.ensure_property(code, "address_roster", row_number, address, row)
                property_ids[code] = prop_id

                if cluster:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO cluster (name, tenant_id) VALUES (?, ?)",
                        (cluster, self.tenant_id),
                    )
                    cluster_id = self.conn.execute(
                        "SELECT cluster_id FROM cluster WHERE name = ? AND tenant_id = ?",
                        (cluster, self.tenant_id),
                    ).fetchone()[0]
                else:
                    cluster_id = None

                qc_assignee_id = self.ensure_stakeholder(qc_assignee)
                self.ensure_stakeholder_role(qc_assignee_id, "QC_INSPECTOR", prop_id)

                if wifi_password:
                    self.handle_sensitive_credential("address_roster", row_number, code, prop_id, "WiFi password", row)
                if door_code:
                    self.handle_sensitive_credential("address_roster", row_number, code, prop_id, "door code", row)

                self.conn.execute(
                    """
                    UPDATE property
                    SET display_name = COALESCE(NULLIF(?, ''), display_name),
                        address_line_1 = COALESCE(NULLIF(?, ''), address_line_1),
                        wifi_ssid = COALESCE(NULLIF(?, ''), wifi_ssid),
                        qc_assignee_stakeholder_id = COALESCE(?, qc_assignee_stakeholder_id),
                        standing_instructions = COALESCE(NULLIF(?, ''), standing_instructions),
                        cluster_id = COALESCE(?, cluster_id),
                        source_system = 'address_roster_csv',
                        updated_at = datetime('now')
                    WHERE property_id = ?
                    """,
                    (display_name, address, wifi_ssid, qc_assignee_id, standing_instructions, cluster_id, prop_id),
                )

                for feature_key, aliases in FEATURE_COLUMNS.items():
                    quantity_raw = self.get_field(row, aliases)
                    quantity = self.parse_quantity(quantity_raw)
                    if quantity is None:
                        continue
                    if quantity <= 0:
                        continue
                    self.upsert_property_feature(prop_id, feature_key, quantity)

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
                arrival_date = self.parse_date(
                    arrival_raw,
                    source_name="master_checklist",
                    row_number=row_number,
                    property_code=code,
                    raw_row=row,
                    property_id=property_id,
                )
                housekeeper = self.get_field(row, ["Cleaner", "Housekeeper", "Assigned Housekeeper"])
                housekeeper_id = self.ensure_stakeholder(housekeeper)
                self.ensure_stakeholder_role(housekeeper_id, "HOUSEKEEPER", property_id)

                self.conn.execute(
                    """
                    INSERT INTO task (property_id, arrival_date, assigned_housekeeper_stakeholder_id, current_stage_definition_id, source_row_number, source_system, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (property_id, arrival_date, housekeeper_id, None, row_number, "master_checklist_csv", self.tenant_id),
                )
                task_id = int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

                latest_stage_definition_id: Optional[int] = None
                for stage_key, aliases in TASK_STAGE_COLUMNS.items():
                    raw_value = self.get_field(row, aliases)
                    parsed = self.parse_bool(
                        raw_value,
                        source_name="master_checklist",
                        row_number=row_number,
                        property_code=code,
                        column_name=aliases[0],
                        raw_row=row,
                        property_id=property_id,
                    )
                    if parsed is None:
                        continue
                    stage_definition_id = self.stage_map.get(stage_key)
                    if stage_definition_id is None:
                        self.error(
                            "missing_stage_definition",
                            "master_checklist",
                            row_number,
                            code,
                            f"No stage definition found for key '{stage_key}'.",
                            row,
                            property_id=property_id,
                        )
                        continue
                    self.conn.execute(
                        """
                        INSERT INTO task_stage_event (task_id, stage_definition_id, is_complete, completed_at, source_value)
                        VALUES (?, ?, ?, CASE WHEN ? = 1 THEN datetime('now') ELSE NULL END, ?)
                        """,
                        (task_id, stage_definition_id, 1 if parsed else 0, 1 if parsed else 0, raw_value),
                    )
                    if parsed:
                        latest_stage_definition_id = stage_definition_id

                self.conn.execute(
                    "UPDATE task SET current_stage_definition_id = ? WHERE task_id = ?",
                    (latest_stage_definition_id, task_id),
                )
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
                    property_id=roster_property_ids[code],
                )

    def persist_issues(self) -> None:
        for issue in self.issues:
            self.conn.execute(
                """
                INSERT INTO migration_issue (issue_type, severity, source_name, row_number, property_code, property_id, message, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue.issue_type,
                    issue.severity,
                    issue.source_name,
                    issue.row_number,
                    issue.property_code,
                    issue.property_id,
                    issue.message,
                    json.dumps(issue.raw_payload, ensure_ascii=False),
                ),
            )


def create_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def run(master_csv: Path, roster_csv: Path, db_path: Path, schema_path: Path, fail_on_error: bool) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
