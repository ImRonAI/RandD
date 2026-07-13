"""Deterministic, resumable legacy SQLite import for DAH-127.

The source is always opened read-only. Every source row is retained in
``legacy_source_record`` before reviewed mappings populate canonical tables.
No checklist section, including ``House Keeping``, is interpreted as a room.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

IMPORT_NAMESPACE = uuid.UUID("54ce5914-9b08-5f43-b88a-0c4f996cf166")
SUPPORTED_TABLES = (
    "cluster", "stakeholder", "role", "property", "stakeholder_role",
    "stage_definition", "task", "task_stage_event", "checklist_template",
    "checklist_category", "checklist_item_template", "inspection",
    "inspection_item_result", "photo_memory", "work_order",
    "work_order_source_item", "report", "inspection_reports",
)
SECRET_COLUMNS = frozenset({
    "wifi_password_ciphertext", "wifi_password_secret_ref",
    "door_code_ciphertext", "door_code_secret_ref",
})


class ImportContractError(RuntimeError):
    """A preflight or reconciliation gate failed."""


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class ImportManifest:
    organization_id: uuid.UUID
    organization_name: str
    portfolio_id: uuid.UUID
    portfolio_name: str
    legacy_timezone: str
    sources: tuple[SourceSpec, ...]
    artifact_root: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "ImportManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        base = path.resolve().parent
        required = ("organization_id", "organization_name", "portfolio_id", "portfolio_name", "legacy_timezone", "sources")
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ImportContractError(f"manifest missing required fields: {', '.join(missing)}")
        sources = []
        for source in raw["sources"]:
            source_path = Path(source["path"])
            if not source_path.is_absolute():
                source_path = base / source_path
            sources.append(SourceSpec(str(source["name"]), source_path.resolve(), str(source["sha256"]).lower()))
        artifact_root = raw.get("artifact_root")
        if artifact_root:
            artifact_root = Path(artifact_root)
            if not artifact_root.is_absolute():
                artifact_root = base / artifact_root
            artifact_root = artifact_root.resolve()
        return cls(
            uuid.UUID(raw["organization_id"]), str(raw["organization_name"]),
            uuid.UUID(raw["portfolio_id"]), str(raw["portfolio_name"]),
            str(raw["legacy_timezone"]), tuple(sources), artifact_root,
        )

    def canonical_sha256(self) -> str:
        payload = {
            "organization_id": str(self.organization_id),
            "organization_name": self.organization_name,
            "portfolio_id": str(self.portfolio_id),
            "portfolio_name": self.portfolio_name,
            "legacy_timezone": self.legacy_timezone,
            "sources": [{"name": s.name, "path": str(s.path), "sha256": s.sha256} for s in self.sources],
            "artifact_root": str(self.artifact_root) if self.artifact_root else None,
        }
        return sha256_json(payload)


@dataclass(frozen=True)
class SourceRow:
    source_system: str
    source_table: str
    source_pk: str
    payload: dict[str, Any]
    checksum: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


def stable_uuid(source_system: str, source_table: str, source_pk: object) -> uuid.UUID:
    return uuid.uuid5(IMPORT_NAMESPACE, f"{source_system}\0{source_table}\0{source_pk}")


def _quote_identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ImportContractError(f"unsafe SQLite identifier: {value!r}")
    return f'"{value}"'


class SQLiteSnapshot:
    def __init__(self, spec: SourceSpec):
        self.spec = spec

    def preflight(self) -> dict[str, Any]:
        if not self.spec.path.is_file():
            raise ImportContractError(f"source does not exist: {self.spec.path}")
        actual = sha256_file(self.spec.path)
        if actual != self.spec.sha256:
            raise ImportContractError(f"source hash mismatch for {self.spec.name}: expected {self.spec.sha256}, got {actual}")
        with self.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchall()
            if integrity != [("ok",)]:
                raise ImportContractError(f"SQLite integrity_check failed for {self.spec.name}")
            tables = sorted(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
            counts = {table: connection.execute(f"SELECT count(*) FROM {_quote_identifier(table)}").fetchone()[0] for table in tables}
            sqlite_version = connection.execute("SELECT sqlite_version()").fetchone()[0]
        return {"name": self.spec.name, "sha256": actual, "size": self.spec.path.stat().st_size,
                "sqlite_version": sqlite_version, "integrity_check": "ok", "tables": counts}

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.spec.path}?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def rows(self) -> Iterable[SourceRow]:
        with self.connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in SUPPORTED_TABLES:
                if table not in tables:
                    continue
                columns = connection.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
                pk_columns = [row[1] for row in columns if row[5]]
                order = ",".join(_quote_identifier(column) for column in pk_columns) if pk_columns else "rowid"
                for ordinal, raw in enumerate(connection.execute(f"SELECT * FROM {_quote_identifier(table)} ORDER BY {order}"), 1):
                    payload = dict(raw)
                    key = "|".join(str(payload.get(column)) for column in pk_columns) if pk_columns else str(ordinal)
                    yield SourceRow(self.spec.name, table, key, payload, sha256_json(payload))


def inventory_manifest(manifest: ImportManifest) -> dict[str, Any]:
    return {"manifest_sha256": manifest.canonical_sha256(), "sources": [SQLiteSnapshot(source).preflight() for source in manifest.sources]}


def safe_diagnostic(row: SourceRow) -> dict[str, str]:
    """Return identifiers only; payloads and encrypted credentials stay out of logs."""
    return {"source_system": row.source_system, "source_table": row.source_table,
            "source_pk": row.source_pk, "source_checksum": row.checksum}


class PostgreSQLImporter:
    def __init__(self, connection: Any, manifest: ImportManifest, run_id: uuid.UUID, *,
                 code_revision: str | None = None, error_limit: int = 0):
        self.connection = connection
        self.manifest = manifest
        self.run_id = run_id
        self.code_revision = code_revision
        self.error_limit = error_limit
        self.org = str(manifest.organization_id)
        self._metrics: dict[tuple[str, str], dict[str, Any]] = {}

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor

    def _tenant(self) -> None:
        self._execute("SELECT set_config('app.org_id', %s, true)", (self.org,))

    def _bootstrap(self) -> None:
        self._tenant()
        self._execute("INSERT INTO organization(id,name) VALUES (%s,%s) ON CONFLICT (id) DO NOTHING",
                      (self.org, self.manifest.organization_name))
        self._tenant()
        self._execute("INSERT INTO portfolio(organization_id,id,name) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                      (self.org, str(self.manifest.portfolio_id), self.manifest.portfolio_name))
        self._execute("""INSERT INTO legacy_import_run(id,organization_id,source_manifest_sha256,mode,code_revision)
                         VALUES (%s,%s,%s,'apply',%s)
                         ON CONFLICT (id) DO UPDATE SET status='running',error_message=NULL""",
                      (str(self.run_id), self.org, self.manifest.canonical_sha256(), self.code_revision))
        self.connection.commit()

    def _raw(self, row: SourceRow) -> bool:
        cursor = self._execute("""INSERT INTO legacy_source_record
          (organization_id,source_system,source_table,source_pk,payload_json,source_checksum,import_run_id)
          VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
          ON CONFLICT (organization_id,source_system,source_table,source_pk) DO NOTHING""",
          (self.org,row.source_system,row.source_table,row.source_pk,json.dumps(row.payload,sort_keys=True,default=str),row.checksum,str(self.run_id)))
        return cursor.rowcount == 1

    def _map(self, row: SourceRow, target_table: str, target_id: object) -> None:
        self._execute("""INSERT INTO legacy_id_map
          (organization_id,source_system,source_table,source_pk,target_table,target_id,source_checksum,import_run_id)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (organization_id,source_system,source_table,source_pk) DO UPDATE
          SET source_checksum=EXCLUDED.source_checksum""",
          (self.org,row.source_system,row.source_table,row.source_pk,target_table,str(target_id),row.checksum,str(self.run_id)))

    def _review(self, row: SourceRow, candidate_type: str, reason: str, evidence: Mapping[str, Any]) -> None:
        self._execute("""INSERT INTO legacy_mapping_review
          (organization_id,import_run_id,source_system,source_table,source_pk,candidate_type,reason_code,source_evidence)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
          (self.org,str(self.run_id),row.source_system,row.source_table,row.source_pk,candidate_type,reason,
           json.dumps(dict(evidence),sort_keys=True,default=str)))

    def _error(self, row: SourceRow, code: str, message: str) -> None:
        self._execute("""INSERT INTO legacy_import_error
          (organization_id,import_run_id,source_system,source_table,source_pk,severity,error_code,message)
          VALUES (%s,%s,%s,%s,%s,'error',%s,%s)""",
          (self.org,str(self.run_id),row.source_system,row.source_table,row.source_pk,code,message))

    def _lookup_map(self, row: SourceRow, source_table: str, source_pk: object) -> str | None:
        cursor = self._execute("""SELECT target_id FROM legacy_id_map WHERE organization_id=%s
          AND source_system=%s AND source_table=%s AND source_pk=%s""",
          (self.org,row.source_system,source_table,str(source_pk)))
        found = cursor.fetchone()
        return found[0] if found else None

    def _system_user(self, source: str) -> str:
        user_id = str(stable_uuid(source,"stakeholder","__importer__"))
        email = f"legacy-import-{hashlib.sha256(source.encode()).hexdigest()[:16]}@invalid.local"
        self._execute("INSERT INTO app_user(id,email,full_name) VALUES (%s,%s,'Legacy Import') ON CONFLICT (id) DO NOTHING", (user_id,email))
        self._execute("""INSERT INTO organization_membership(organization_id,user_id,role)
                         VALUES (%s,%s,'ORG_ADMIN') ON CONFLICT DO NOTHING""", (self.org,user_id))
        return user_id

    def _load(self, row: SourceRow) -> tuple[str | None, str | None]:
        p = row.payload
        if row.source_table == "property":
            home_id = str(stable_uuid(row.source_system,"property",row.source_pk))
            address = ", ".join(str(p.get(k)).strip() for k in ("address_line_1","city","state_province","postal_code") if p.get(k))
            cluster = self._cluster_name(row, p.get("cluster_id"))
            self._execute("""INSERT INTO home(organization_id,id,portfolio_id,unit_code,name,legacy_property_id,
              formatted_address,cluster_name,wifi_ssid,wifi_password_ciphertext,wifi_password_secret_ref,
              door_code_ciphertext,door_code_secret_ref,standing_instructions,roster_active,legacy_source_system,created_at,updated_at)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamptz,now()),COALESCE(%s::timestamptz,now()))
              ON CONFLICT (organization_id,id) DO NOTHING""",
              (self.org,home_id,str(self.manifest.portfolio_id),p.get("unit_code"),p.get("display_name") or p.get("unit_code") or f"Legacy {row.source_pk}",
               row.source_pk,address or None,cluster,p.get("wifi_ssid"),p.get("wifi_password_ciphertext"),p.get("wifi_password_secret_ref"),
               p.get("door_code_ciphertext"),p.get("door_code_secret_ref"),p.get("standing_instructions"),bool(p.get("roster_active",1)),
               p.get("source_system") or row.source_system,p.get("created_at"),p.get("updated_at")))
            self._map(row,"home",home_id); return "home",home_id
        if row.source_table == "stakeholder":
            user_id = str(stable_uuid(row.source_system,"stakeholder",row.source_pk))
            email = p.get("email") or f"legacy-{hashlib.sha256(f'{row.source_system}:{row.source_pk}'.encode()).hexdigest()[:20]}@invalid.local"
            self._execute("""INSERT INTO app_user(id,email,full_name,phone,active,created_at) VALUES (%s,%s,%s,%s,%s,COALESCE(%s::timestamptz,now()))
              ON CONFLICT (id) DO NOTHING""",(user_id,email,p.get("full_name"),p.get("phone"),bool(p.get("is_active",1)),p.get("created_at")))
            self._map(row,"app_user",user_id); return "app_user",user_id
        if row.source_table == "stakeholder_role":
            user_id=self._lookup_map(row,"stakeholder",p.get("stakeholder_id")); role=self._role_key(row,p.get("role_id"))
            if not user_id or not role:
                raise ImportContractError("stakeholder role parent mapping missing")
            self._execute("INSERT INTO organization_membership(organization_id,user_id,role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",(self.org,user_id,role))
            property_id=p.get("property_id")
            if property_id is not None:
                home_id=self._lookup_map(row,"property",property_id)
                if not home_id: raise ImportContractError("property-scoped role home mapping missing")
                permission="read" if role=="OWNER" else "manage"
                self._execute("INSERT INTO home_grant(organization_id,home_id,user_id,permission) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",(self.org,home_id,user_id,permission))
            target=f"{user_id}:{role}:{property_id if property_id is not None else 'global'}"; self._map(row,"organization_membership",target); return "organization_membership",target
        if row.source_table == "task":
            home_id=self._lookup_map(row,"property",p.get("property_id"))
            if not home_id: raise ImportContractError("task home mapping missing")
            task_id=f"legacy:{row.source_system}:{row.source_pk}"; assignee=self._lookup_map(row,"stakeholder",p.get("assigned_housekeeper_stakeholder_id")) if p.get("assigned_housekeeper_stakeholder_id") else None
            stages=self._stage_events(row,p.get("task_id"))
            current=next((item["stage_key"] for item in reversed(stages) if item.get("is_complete")),None)
            self._execute("""INSERT INTO field_task(organization_id,id,home_id,arrival_date,stage_name,assignee,assigned_housekeeper_user_id,
              legacy_source_row_number,legacy_source_system,legacy_stage_events,created_at,updated_at)
              VALUES (%s,%s,%s,%s::date,%s,%s,%s,%s,%s,%s::jsonb,COALESCE(%s::timestamptz,now()),COALESCE(%s::timestamptz,now())) ON CONFLICT DO NOTHING""",
              (self.org,task_id,home_id,p.get("arrival_date"),current,None,assignee,p.get("source_row_number"),p.get("source_system") or row.source_system,json.dumps(stages),p.get("created_at"),p.get("updated_at")))
            self._map(row,"field_task",task_id); return "field_task",task_id
        if row.source_table == "inspection":
            task_id=self._lookup_map(row,"task",p.get("task_id"));
            if not task_id: raise ImportContractError("inspection task mapping missing")
            cursor=self._execute("SELECT home_id FROM field_task WHERE organization_id=%s AND id=%s",(self.org,task_id)); home_id=str(cursor.fetchone()[0])
            inspector=self._lookup_map(row,"stakeholder",p.get("inspector_stakeholder_id")) if p.get("inspector_stakeholder_id") else self._system_user(row.source_system)
            inspection_id=str(stable_uuid(row.source_system,"inspection",row.source_pk)); status="completed" if p.get("submitted_at") else "in_progress"
            self._execute("""INSERT INTO inspection(organization_id,id,home_id,inspection_type,status,client_id,created_by,task_id,started_at,completed_at)
              VALUES (%s,%s,%s,'turnover',%s,%s,%s,%s,COALESCE(%s::timestamptz,now()),%s::timestamptz) ON CONFLICT DO NOTHING""",
              (self.org,inspection_id,home_id,status,f"legacy:{row.source_system}:{row.source_pk}",inspector,task_id,p.get("started_at"),p.get("submitted_at")))
            self._map(row,"inspection",inspection_id); return "inspection",inspection_id
        if row.source_table == "inspection_item_result":
            inspection_id=self._lookup_map(row,"inspection",p.get("inspection_id")); item_key=self._item_key(row,p.get("checklist_item_template_id"))
            if not inspection_id or not item_key: raise ImportContractError("inspection result parent or checklist mapping missing")
            cursor=self._execute("SELECT home_id,created_by FROM inspection WHERE organization_id=%s AND id=%s",(self.org,inspection_id)); home_id,recorded_by=cursor.fetchone()
            result_id=str(stable_uuid(row.source_system,"inspection_item_result",row.source_pk))
            self._execute("""INSERT INTO inspection_item_result(organization_id,id,home_id,inspection_id,item_key,result,note,recorded_by,client_id,created_at)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamptz,now())) ON CONFLICT DO NOTHING""",
              (self.org,result_id,str(home_id),inspection_id,item_key,p.get("result"),p.get("notes") or "",str(recorded_by),f"legacy:{row.source_system}:{row.source_pk}",p.get("observed_at")))
            self._map(row,"inspection_item_result",result_id); return "inspection_item_result",result_id
        if row.source_table == "photo_memory":
            uri=p.get("storage_ref") or p.get("uri")
            status="unverified"
            byte_size=None
            if uri and self.manifest.artifact_root and not str(uri).startswith(("s3://","http://","https://","data:")):
                candidate=(self.manifest.artifact_root / str(uri)).resolve()
                if candidate.is_relative_to(self.manifest.artifact_root):
                    if candidate.is_file(): status="present";byte_size=candidate.stat().st_size
                    else: status="missing"
            self._execute("""INSERT INTO legacy_artifact_manifest(organization_id,import_run_id,source_system,source_table,source_pk,
              artifact_kind,source_uri,sha256,byte_size,validation_status) VALUES (%s,%s,%s,%s,%s,'photo',%s,%s,%s,%s)
              ON CONFLICT DO NOTHING""",(self.org,str(self.run_id),row.source_system,row.source_table,row.source_pk,uri,p.get("content_hash"),byte_size,status))
            self._map(row,"legacy_source_record",f"{row.source_system}:{row.source_table}:{row.source_pk}")
            return "legacy_artifact_manifest",row.source_pk
        if row.source_table == "inspection_reports":
            return self._report(row)
        return None,None

    def _cluster_name(self,row:SourceRow,cluster_id:object)->str|None:
        if cluster_id is None:return None
        # Raw cluster rows have already been retained; query their JSON safely.
        cursor=self._execute("""SELECT payload_json->>'name' FROM legacy_source_record WHERE organization_id=%s AND source_system=%s
          AND source_table='cluster' AND source_pk=%s""",(self.org,row.source_system,str(cluster_id)))
        found=cursor.fetchone();return found[0] if found else None

    def _role_key(self,row:SourceRow,role_id:object)->str|None:
        cursor=self._execute("""SELECT payload_json->>'role_key' FROM legacy_source_record WHERE organization_id=%s AND source_system=%s
          AND source_table='role' AND source_pk=%s""",(self.org,row.source_system,str(role_id)))
        found=cursor.fetchone();return found[0] if found else None

    def _stage_events(self,row:SourceRow,task_id:object)->list[dict[str,Any]]:
        cursor=self._execute("""SELECT event.payload_json, definition.payload_json->>'stage_key'
          FROM legacy_source_record event LEFT JOIN legacy_source_record definition
          ON definition.organization_id=event.organization_id AND definition.source_system=event.source_system
          AND definition.source_table='stage_definition' AND definition.source_pk=event.payload_json->>'stage_definition_id'
          WHERE event.organization_id=%s AND event.source_system=%s AND event.source_table='task_stage_event'
          AND event.payload_json->>'task_id'=%s ORDER BY (event.payload_json->>'stage_event_id')::bigint""",(self.org,row.source_system,str(task_id)))
        return [dict(payload,stage_key=stage_key) for payload,stage_key in cursor.fetchall()]

    def _item_key(self,row:SourceRow,item_id:object)->str|None:
        cursor=self._execute("""SELECT ci.item_key FROM legacy_source_record item
          JOIN legacy_source_record category ON category.organization_id=item.organization_id AND category.source_system=item.source_system
            AND category.source_table='checklist_category' AND category.source_pk=item.payload_json->>'checklist_category_id'
          JOIN checklist_item ci ON ci.section_name=category.payload_json->>'category_name' AND ci.label=item.payload_json->>'item_text'
          WHERE item.organization_id=%s AND item.source_system=%s AND item.source_table='checklist_item_template' AND item.source_pk=%s""",
          (self.org,row.source_system,str(item_id)))
        found=cursor.fetchone();return found[0] if found else None

    def _report(self,row:SourceRow)->tuple[str,str]:
        p=row.payload; property_label=(p.get("property") or "").strip(); mapping="mapped"
        if not property_label:
            mapping="quarantined"; self._review(row,"report_property","blank_property",{"property":""})
        else:
            cursor=self._execute("""SELECT id FROM home WHERE organization_id=%s AND (lower(unit_code)=lower(%s) OR lower(name)=lower(%s))""",(self.org,property_label,property_label))
            matches=cursor.fetchall()
            if len(matches)!=1:
                mapping="review_required"; self._review(row,"report_property","ambiguous_or_unknown_property",{"property":property_label,"match_count":len(matches)})
        state=p.get("state_json") or "{}"
        try: parsed=json.loads(state)
        except (TypeError,json.JSONDecodeError):
            parsed={"legacy_unparsed_state":str(state)}; mapping="quarantined"; self._error(row,"invalid_report_json","Historical report state_json is not valid JSON")
        sections=parsed.get("sections",[]) if isinstance(parsed,dict) else []
        if any(any(token in str(section.get("title") or section.get("name") or section.get("id") or "").lower().replace("-"," ")
                   for token in ("house keeping","housekeeping")) for section in sections if isinstance(section,dict)):
            self._review(row,"house_keeping_section","no_room_inference",{"section_label":"House Keeping"})
        report_id=str(p.get("form_uuid") or row.source_pk)
        self._execute("""INSERT INTO legacy_inspection_report(organization_id,id,property,state_json,created_at,source_system,source_checksum,updated_at,signed_off,artifact_uri,mapping_status)
          VALUES (%s,%s,%s,%s::jsonb,COALESCE(%s::timestamptz,now()),%s,%s,%s::timestamptz,%s,%s,%s)
          ON CONFLICT (organization_id,id) DO UPDATE SET state_json=EXCLUDED.state_json,updated_at=EXCLUDED.updated_at,source_checksum=EXCLUDED.source_checksum,mapping_status=EXCLUDED.mapping_status""",
          (self.org,report_id,p.get("property"),json.dumps(parsed,sort_keys=True),p.get("created_utc"),row.source_system,row.checksum,p.get("updated_utc"),bool(p.get("signed_off")),p.get("s3_artifact_uri"),mapping))
        uri=p.get("s3_artifact_uri")
        if uri:
            self._execute("""INSERT INTO legacy_artifact_manifest(organization_id,import_run_id,source_system,source_table,source_pk,artifact_kind,source_uri,validation_status)
              VALUES (%s,%s,%s,%s,%s,'historical_report',%s,'unverified') ON CONFLICT DO NOTHING""",(self.org,str(self.run_id),row.source_system,row.source_table,row.source_pk,uri))
        self._map(row,"legacy_inspection_report",report_id);return "legacy_inspection_report",report_id

    def run(self, snapshots: Sequence[SQLiteSnapshot], *, fail_after_table: str | None = None) -> dict[str,Any]:
        self._bootstrap()
        extracted=list(row for snapshot in snapshots for row in snapshot.rows())
        groups={(source.spec.name,table):[row for row in extracted if row.source_system==source.spec.name and row.source_table==table]
                for source in snapshots for table in SUPPORTED_TABLES}
        try:
            # Retain every row first. Mappings may depend on lookup tables that
            # sort after their parents (for example task_stage_event).
            novelty: dict[tuple[str,str], tuple[int,int]] = {}
            self._tenant()
            for key,rows in groups.items():
                inserted=existing=0
                for row in rows:
                    is_new=self._raw(row);inserted+=int(is_new);existing+=int(not is_new)
                novelty[key]=(inserted,existing)
            self.connection.commit()
            for (source_system,table),rows in groups.items():
                inserted,existing=novelty[(source_system,table)];quarantined=0;digest=hashlib.sha256()
                self._tenant()
                for row in rows:
                    digest.update((row.checksum+"\n").encode())
                    try:self._load(row)
                    except ImportContractError as error:
                        quarantined+=1;self._error(row,"mapping_error",str(error));self._review(row,"unmapped_record","mapping_error",safe_diagnostic(row))
                self._execute("""INSERT INTO legacy_import_metric(organization_id,import_run_id,source_system,entity,extracted_count,inserted_count,existing_count,quarantined_count,source_checksum)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (import_run_id,source_system,entity) DO UPDATE SET
                  extracted_count=EXCLUDED.extracted_count,inserted_count=EXCLUDED.inserted_count,existing_count=EXCLUDED.existing_count,
                  quarantined_count=EXCLUDED.quarantined_count,source_checksum=EXCLUDED.source_checksum""",
                  (self.org,str(self.run_id),source_system,table,len(rows),inserted,existing,quarantined,digest.hexdigest()))
                self._execute("UPDATE legacy_import_run SET checkpoint=jsonb_set(checkpoint,'{last_table}',to_jsonb(%s::text),true) WHERE id=%s",(table,str(self.run_id)))
                self.connection.commit()
                if fail_after_table==table: raise RuntimeError(f"injected interruption after {table}")
            self._tenant(); cursor=self._execute("SELECT count(*) FROM legacy_import_error WHERE import_run_id=%s AND severity='error'",(str(self.run_id),)); errors=cursor.fetchone()[0]
            if errors>self.error_limit: raise ImportContractError(f"error limit exceeded: {errors} > {self.error_limit}")
            summary={"source_rows":len(extracted),"errors":errors,"manifest_sha256":self.manifest.canonical_sha256()}
            self._execute("UPDATE legacy_import_run SET status='completed',finished_at=now(),summary=%s::jsonb WHERE id=%s",(json.dumps(summary,sort_keys=True),str(self.run_id)));self.connection.commit();return summary
        except Exception as error:
            self.connection.rollback();self._tenant();self._execute("UPDATE legacy_import_run SET status='failed',finished_at=now(),error_message=%s WHERE id=%s",(str(error)[:1000],str(self.run_id)));self.connection.commit();raise


def connect_postgres(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as error:
        raise ImportContractError("apply mode requires psycopg 3; install psycopg[binary]") from error
    return psycopg.connect(database_url)


def run_from_environment() -> dict[str, Any]:
    manifest_path=os.environ.get("LEGACY_SOURCE_MANIFEST"); mode=os.environ.get("IMPORT_MODE","plan")
    if not manifest_path: raise ImportContractError("LEGACY_SOURCE_MANIFEST is required")
    if mode not in {"plan","validate","apply"}: raise ImportContractError("IMPORT_MODE must be plan, validate, or apply")
    manifest=ImportManifest.load(Path(manifest_path)); inventory=inventory_manifest(manifest)
    if mode in {"plan","validate"}: return {"mode":mode,**inventory,"writes":0}
    database_url=os.environ.get("DATABASE_URL")
    if not database_url: raise ImportContractError("DATABASE_URL is required in apply mode")
    run_id=uuid.UUID(os.environ["IMPORT_RUN_ID"]) if os.environ.get("IMPORT_RUN_ID") else uuid.uuid4()
    with connect_postgres(database_url) as connection:
        summary=PostgreSQLImporter(connection,manifest,run_id,code_revision=os.environ.get("CODE_REVISION"),error_limit=int(os.environ.get("IMPORT_ERROR_LIMIT","0"))).run([SQLiteSnapshot(source) for source in manifest.sources])
    return {"mode":"apply","run_id":str(run_id),**summary}
