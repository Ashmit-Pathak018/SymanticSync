"""
backend/api/routes_conflicts.py
────────────────────────────────
Endpoints for conflict inspection and manual/automatic resolution.

Endpoints
---------
POST /api/v1/conflicts/detect   → Detect conflicts across two replicas
POST /api/v1/conflicts/resolve  → Resolve a conflict (auto, pick_a, pick_b, custom)
GET  /api/v1/conflicts          → List all detected conflicts (filterable)
GET  /api/v1/conflicts/{id}     → Get details of a single conflict
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

from backend.api.models import (
    ConflictDetectRequest,
    ConflictResolveRequest,
)
from backend.api.state import app_state
from backend.engine.mutation_lock import serialized_mutation
from backend.engine.conflict_detector import ConflictDetector
from backend.engine.merge_manager import MergeManager
from backend.engine.policy_registry import parse_bounded_sum_bounds, policy_base_name
from backend.engine.semantic_resolver import SemanticResolver, ResolutionError
from backend.engine.crdt_sync import _row_dependency_ids
from backend.engine.log_compaction import ensure_compaction_tables
from backend.engine.fk_quarantine import (
    enable_foreign_keys, ensure_quarantine_table, quarantine_orphans, verify_fk_integrity,
)

router = APIRouter(tags=["Conflicts"])
_detector = ConflictDetector()
_manager = MergeManager(app_state=app_state)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _write_resolution_atomically(
    replica_a_path: str,
    replica_b_path: str,
    table: str,
    row_id: Any,
    column: str,
    resolved_value: Any,
    replica_a_id: str = "replica_a",
    replica_b_id: str = "replica_b",
    bounded_bounds: tuple[int | float, int | float] | None = None,
) -> None:
    """Apply a conflict resolution to both replicas in one SQLite transaction."""
    import json
    import os
    import sqlite3
    import uuid
    from datetime import datetime, timezone

    if os.path.normcase(os.path.realpath(replica_a_path)) == os.path.normcase(
        os.path.realpath(replica_b_path)
    ):
        raise HTTPException(status_code=409, detail="Conflict replicas must use distinct database files.")

    quote = _quote_identifier
    try:
        with sqlite3.connect(replica_a_path, timeout=10.0) as conn:
            enable_foreign_keys(conn)
            conn.execute("ATTACH DATABASE ? AS replica_b", (replica_b_path,))
            ensure_quarantine_table(conn, "main")
            ensure_quarantine_table(conn, "replica_b")
            conn.execute("BEGIN IMMEDIATE")
            modes = [
                conn.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0].lower()
                for schema in ("main", "replica_b")
            ]
            if any(mode == "wal" for mode in modes):
                raise HTTPException(
                    status_code=409,
                    detail="Atomic two-replica resolution requires rollback-journal SQLite databases.",
                )

            table_info: dict[str, list[tuple[Any, ...]]] = {}
            for schema in ("main", "replica_b"):
                conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {schema}._ss_change_log (
                        id TEXT PRIMARY KEY, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
                        column_name TEXT NOT NULL, old_value TEXT, new_value TEXT,
                        ts_pt REAL NOT NULL, ts_l INTEGER NOT NULL DEFAULT 0,
                        replica_id TEXT NOT NULL, applied_at TEXT NOT NULL,
                        op_type TEXT NOT NULL DEFAULT 'UPDATE', origin_id TEXT, sequence INTEGER,
                        source_id TEXT, source_sequence INTEGER, depends_on TEXT NOT NULL DEFAULT '[]'
                    )"""
                )
                log_cols = {
                    row[1] for row in conn.execute(f"PRAGMA {schema}.table_info('_ss_change_log')")
                }
                if "op_type" not in log_cols:
                    conn.execute(
                        f"ALTER TABLE {schema}._ss_change_log "
                        "ADD COLUMN op_type TEXT NOT NULL DEFAULT 'UPDATE'"
                    )
                if "origin_id" not in log_cols:
                    conn.execute(f"ALTER TABLE {schema}._ss_change_log ADD COLUMN origin_id TEXT")
                if "sequence" not in log_cols:
                    conn.execute(f"ALTER TABLE {schema}._ss_change_log ADD COLUMN sequence INTEGER")
                for col, ddl in (("source_id", "TEXT"), ("source_sequence", "INTEGER"),
                                 ("depends_on", "TEXT NOT NULL DEFAULT '[]'"),
                                 ("bounded_delta", "NUMERIC"),
                                 ("bounds_min", "NUMERIC"),
                                 ("bounds_max", "NUMERIC")):
                    if col not in log_cols:
                        conn.execute(f"ALTER TABLE {schema}._ss_change_log ADD COLUMN {col} {ddl}")
                conn.execute(
                    f"UPDATE {schema}._ss_change_log SET sequence = rowid WHERE sequence IS NULL"
                )
                conn.execute(f"UPDATE {schema}._ss_change_log SET origin_id=id WHERE origin_id IS NULL OR origin_id='' ")
                conn.execute(f"UPDATE {schema}._ss_change_log SET source_id=replica_id WHERE source_id IS NULL OR source_id='' ")
                conn.execute(f"UPDATE {schema}._ss_change_log SET source_sequence=sequence WHERE source_sequence IS NULL")
                ensure_compaction_tables(conn, schema)
                conn.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {schema}._ss_change_log_sequence_idx "
                    f"ON _ss_change_log(sequence)"
                )
                info = conn.execute(
                    f"PRAGMA {schema}.table_info({quote(table)})"
                ).fetchall()
                if not info:
                    raise HTTPException(status_code=409, detail=f"Table '{table}' is missing from {schema}.")
                pks = [row[1] for row in info if row[5] > 0]
                if len(pks) != 1:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot resolve '{table}': table must have a single-column primary key.",
                    )
                table_info[schema] = info

            pk_a = next(row[1] for row in table_info["main"] if row[5] > 0)
            pk_b = next(row[1] for row in table_info["replica_b"] if row[5] > 0)
            if pk_a != pk_b:
                raise HTTPException(status_code=409, detail=f"Primary-key schemas differ for '{table}'.")
            pk_col = pk_a
            operation_id = str(uuid.uuid4())
            operation_time = time.time()
            applied_at = datetime.now(timezone.utc).isoformat()
            replica_ids = {"main": replica_a_id, "replica_b": replica_b_id}

            def read_row(schema: str) -> dict[str, Any] | None:
                cols = [row[1] for row in table_info[schema]]
                row = conn.execute(
                    f"SELECT * FROM {schema}.{quote(table)} WHERE {quote(pk_col)} = ?",
                    (row_id,),
                ).fetchone()
                return dict(zip(cols, row)) if row is not None else None

            old_snapshots = {replica_ids[schema]: read_row(schema) for schema in ("main", "replica_b")}
            depends_on = sorted({
                dep for schema in ("main", "replica_b")
                for dep in _row_dependency_ids(conn, table, row_id, schema)
            })
            source_id = "resolution:" + ":".join(sorted((replica_a_id, replica_b_id)))
            source_sequence = max(
                int(conn.execute(
                    f"SELECT COALESCE(MAX(source_sequence),0) FROM ("
                    f"SELECT source_sequence FROM {schema}._ss_change_log WHERE source_id=? UNION ALL "
                    f"SELECT source_sequence FROM {schema}._ss_compacted_receipts WHERE source_id=?)",
                    (source_id, source_id),
                ).fetchone()[0])
                for schema in ("main", "replica_b")
            ) + 1
            if column == "*" and resolved_value is None:
                resolution_payload = {"kind": "delete"}
            elif column == "*" and isinstance(resolved_value, dict):
                resolution_payload = {"kind": "row", "value": resolved_value}
            else:
                resolution_payload = {"kind": "cell", "column": column, "value": resolved_value}
                if bounded_bounds is not None:
                    resolution_payload["bounds"] = {"min": bounded_bounds[0], "max": bounded_bounds[1]}

            def log_change(schema: str) -> None:
                sequence = conn.execute(
                    f"SELECT COALESCE(MAX(sequence),0)+1 FROM ("
                    f"SELECT sequence FROM {schema}._ss_change_log UNION ALL "
                    f"SELECT sequence FROM {schema}._ss_compacted_receipts)"
                ).fetchone()[0]
                res_min = bounded_bounds[0] if bounded_bounds is not None else None
                res_max = bounded_bounds[1] if bounded_bounds is not None else None
                conn.execute(
                    f"""INSERT INTO {schema}._ss_change_log
                        (id, table_name, row_id, column_name, old_value, new_value,
                         ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence,
                         source_id, source_sequence, depends_on, bounded_delta, bounds_min, bounds_max)
                        VALUES (?, ?, ?, '*', ?, ?, ?, 0, ?, ?, 'RESOLVE', ?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (
                        str(uuid.uuid4()), table, str(row_id),
                        json.dumps(old_snapshots, default=str), json.dumps(resolution_payload, default=str),
                        operation_time, replica_ids[schema], applied_at, operation_id, sequence,
                        source_id, source_sequence, json.dumps(depends_on),
                        res_min, res_max,
                    ),
                )

            if column == "*" and resolved_value is None:
                for schema in ("main", "replica_b"):
                    old_row = read_row(schema)
                    if old_row is None:
                        prior = conn.execute(
                            f"SELECT old_value FROM {schema}._ss_change_log "
                            "WHERE table_name = ? AND row_id = ? AND op_type = 'DELETE' "
                            "AND old_value IS NOT NULL ORDER BY sequence DESC LIMIT 1",
                            (table, str(row_id)),
                        ).fetchone()
                        if prior:
                            try:
                                prior_row = json.loads(prior[0])
                            except (TypeError, ValueError):
                                prior_row = None
                            if isinstance(prior_row, dict):
                                old_row = prior_row
                    if old_row is not None:
                        quarantine_orphans(conn, table, row_id, schema=schema)
                    conn.execute(
                        f"DELETE FROM {schema}.{quote(table)} WHERE {quote(pk_col)} = ?",
                        (row_id,),
                    )
                    if read_row(schema) is not None:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Delete resolution did not remove row {row_id!r} from {schema}.",
                        )
                    log_change(schema)
                verify_fk_integrity(conn, "main")
                verify_fk_integrity(conn, "replica_b")
            elif column == "*" and isinstance(resolved_value, dict):
                cols = list(resolved_value)
                valid_cols = {row[1] for row in table_info["main"]}
                if set(cols) != valid_cols or pk_col not in resolved_value:
                    raise HTTPException(status_code=409, detail="Resolved row payload does not match the table schema.")
                if resolved_value[pk_col] != row_id:
                    raise HTTPException(status_code=409, detail="Resolved row primary key does not match the conflict row.")
                insert_cols = ", ".join(quote(col) for col in cols)
                placeholders = ", ".join("?" for _ in cols)
                update_cols = [col for col in cols if col != pk_col]
                if update_cols:
                    update_sql = ", ".join(f"{quote(col)} = excluded.{quote(col)}" for col in update_cols)
                    conflict_sql = f"DO UPDATE SET {update_sql}"
                else:
                    conflict_sql = "DO NOTHING"
                for schema in ("main", "replica_b"):
                    old_row = read_row(schema)
                    conn.execute(
                        f"INSERT INTO {schema}.{quote(table)} ({insert_cols}) VALUES ({placeholders}) "
                        f"ON CONFLICT ({quote(pk_col)}) {conflict_sql}",
                        [resolved_value[col] for col in cols],
                    )
                    persisted = read_row(schema)
                    if persisted != resolved_value:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Resolved row payload was not fully applied in {schema}.",
                        )
                    log_change(schema)
                verify_fk_integrity(conn, "main")
                verify_fk_integrity(conn, "replica_b")
            else:
                valid_cols = {row[1] for row in table_info["main"]}
                if column not in valid_cols:
                    raise HTTPException(status_code=409, detail=f"Column '{column}' is missing from '{table}'.")
                for schema in ("main", "replica_b"):
                    old_row = read_row(schema)
                    if old_row is None:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Cannot resolve '{table}' row {row_id!r}: missing from {schema}.",
                        )
                    if bounded_bounds is not None and not (bounded_bounds[0] <= resolved_value <= bounded_bounds[1]):
                        raise HTTPException(
                            status_code=409,
                            detail="BOUNDED_SUM resolution value violates inclusive bounds.",
                        )
                    cursor = conn.execute(
                        f"UPDATE {schema}.{quote(table)} SET {quote(column)} = ? "
                        f"WHERE {quote(pk_col)} = ?",
                        (resolved_value, row_id),
                    )
                    if cursor.rowcount != 1:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Resolution did not update exactly one row in {schema}.",
                        )
                    persisted = read_row(schema)
                    if persisted is None or persisted.get(column) != resolved_value:
                        raise HTTPException(status_code=409, detail=f"Resolution value did not persist in {schema}.")
                    log_change(schema)
                verify_fk_integrity(conn, "main")
                verify_fk_integrity(conn, "replica_b")
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Atomic conflict write-back failed: {exc}") from exc


def _write_insert_collision_atomically(
    replica_a_path: str,
    replica_b_path: str,
    record: dict[str, Any],
    resolved_value: dict[str, Any],
    replica_a_id: str,
    replica_b_id: str,
) -> dict[str, Any]:
    """Resolve an INSERT collision as one auditable two-database operation.

    The conflict snapshots identify the only rows this operation may replace.
    For secondary-UNIQUE collisions the losing row is deleted explicitly on
    both replicas; the complete chosen/custom row is then installed on both.
    Any unexpected row, schema mismatch, UNIQUE violation, or trigger failure
    aborts the attached-database transaction.
    """
    import hashlib
    import json
    import os
    import sqlite3
    import uuid
    from datetime import datetime, timezone

    table = record["table"]
    conflict_id = record["conflict_id"]
    payload_a = record.get("value_a")
    payload_b = record.get("value_b")
    if not isinstance(payload_a, dict) or not isinstance(payload_b, dict):
        raise HTTPException(status_code=409, detail="INSERT conflict is missing a complete row snapshot.")
    if os.path.normcase(os.path.realpath(replica_a_path)) == os.path.normcase(
        os.path.realpath(replica_b_path)
    ):
        raise HTTPException(status_code=409, detail="Conflict replicas must use distinct database files.")

    quote = _quote_identifier
    resolution_json = json.dumps(resolved_value, sort_keys=True, separators=(",", ":"), default=str)
    source_id = "resolution:" + ":".join(sorted((replica_a_id, replica_b_id)))
    operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"semanticsync:insert-resolution:{conflict_id}"))
    try:
        with sqlite3.connect(replica_a_path, timeout=10.0) as conn:
            enable_foreign_keys(conn)
            conn.execute("ATTACH DATABASE ? AS replica_b", (replica_b_path,))
            conn.execute("BEGIN IMMEDIATE")
            schemas = ("main", "replica_b")
            if any(conn.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0].lower() == "wal" for schema in schemas):
                raise HTTPException(status_code=409, detail="Atomic two-replica resolution requires rollback-journal SQLite databases.")

            infos: dict[str, list[sqlite3.Row]] = {}
            for schema in schemas:
                info = conn.execute(f"PRAGMA {schema}.table_info({quote(table)})").fetchall()
                if not info:
                    raise HTTPException(status_code=409, detail=f"Table '{table}' is missing from {schema}.")
                pks = [row[1] for row in info if row[5] > 0]
                if len(pks) != 1:
                    raise HTTPException(status_code=409, detail=f"Cannot resolve '{table}': table must have a single-column primary key.")
                infos[schema] = info
                cols = {row[1] for row in info}
                if set(payload_a) != cols or set(payload_b) != cols or set(resolved_value) != cols:
                    raise HTTPException(status_code=409, detail="INSERT conflict payloads must contain every table column exactly once.")

            pk = next(row[1] for row in infos["main"] if row[5] > 0)
            if pk != next(row[1] for row in infos["replica_b"] if row[5] > 0):
                raise HTTPException(status_code=409, detail=f"Primary-key schemas differ for '{table}'.")
            if payload_a[pk] == payload_b[pk]:
                participant_ids = [payload_a[pk]]
            else:
                participant_ids = [payload_a[pk], payload_b[pk]]
            participant_ids = list(dict.fromkeys(participant_ids))
            if resolved_value.get(pk) is None:
                raise HTTPException(status_code=409, detail="Resolved INSERT payload must contain a non-null primary key.")

            def read_row(schema: str, row_id: Any) -> dict[str, Any] | None:
                columns = [row[1] for row in infos[schema]]
                row = conn.execute(
                    f"SELECT * FROM {schema}.{quote(table)} WHERE {quote(pk)} = ?", (row_id,)
                ).fetchone()
                return dict(zip(columns, row)) if row is not None else None

            # Upgrade older logs before querying stable operation identity.
            for schema in schemas:
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema}._ss_change_log ("
                    "id TEXT PRIMARY KEY, table_name TEXT NOT NULL, row_id TEXT NOT NULL, "
                    "column_name TEXT NOT NULL, old_value TEXT, new_value TEXT, ts_pt REAL NOT NULL, "
                    "ts_l INTEGER NOT NULL DEFAULT 0, replica_id TEXT NOT NULL, applied_at TEXT NOT NULL, "
                    "op_type TEXT NOT NULL DEFAULT 'UPDATE', origin_id TEXT, sequence INTEGER, "
                    "source_id TEXT, source_sequence INTEGER, depends_on TEXT NOT NULL DEFAULT '[]')"
                )
                log_cols = {row[1] for row in conn.execute(f"PRAGMA {schema}.table_info('_ss_change_log')")}
                for name, ddl in (("op_type", "TEXT NOT NULL DEFAULT 'UPDATE'"), ("origin_id", "TEXT"),
                                  ("sequence", "INTEGER"), ("source_id", "TEXT"),
                                  ("source_sequence", "INTEGER"), ("depends_on", "TEXT NOT NULL DEFAULT '[]'")):
                    if name not in log_cols:
                        conn.execute(f"ALTER TABLE {schema}._ss_change_log ADD COLUMN {name} {ddl}")
                conn.execute(f"UPDATE {schema}._ss_change_log SET sequence=rowid WHERE sequence IS NULL")
                conn.execute(f"UPDATE {schema}._ss_change_log SET origin_id=id WHERE origin_id IS NULL OR origin_id='' ")
                conn.execute(f"UPDATE {schema}._ss_change_log SET source_id=replica_id WHERE source_id IS NULL OR source_id='' ")
                conn.execute(f"UPDATE {schema}._ss_change_log SET source_sequence=sequence WHERE source_sequence IS NULL")
                ensure_compaction_tables(conn, schema)

            existing_ops = {}
            for schema in schemas:
                existing_ops[schema] = conn.execute(
                    f"SELECT new_value FROM {schema}._ss_change_log WHERE origin_id=? AND op_type='RESOLVE'",
                    (operation_id,),
                ).fetchone() if conn.execute(
                    "SELECT 1 FROM " + schema + ".sqlite_master WHERE type='table' AND name='_ss_change_log'"
                ).fetchone() else None
            if any(existing_ops.values()):
                if not all(existing_ops.values()) or any(json.loads(row[0]).get("value") != resolved_value for row in existing_ops.values()):
                    raise HTTPException(status_code=409, detail="Resolution operation identity has inconsistent receipts.")
                for schema in schemas:
                    actual = read_row(schema, resolved_value[pk])
                    if actual != resolved_value:
                        raise HTTPException(status_code=409, detail="Previously accepted resolution no longer matches replica state.")
                return {"operation_id": operation_id, "source_id": source_id, "source_sequence": None, "replayed": True}

            allowed = [payload_a, payload_b]
            observed_payloads: set[str] = set()
            for schema in schemas:
                for row_id in participant_ids:
                    actual = read_row(schema, row_id)
                    if actual is not None and actual not in allowed:
                        raise HTTPException(status_code=409, detail=f"Participant row {row_id!r} changed since conflict detection in {schema}; refusing overwrite.")
                    if actual in allowed:
                        observed_payloads.add(json.dumps(actual, sort_keys=True, separators=(",", ":"), default=str))
            expected_payloads = {
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
                for payload in allowed
            }
            if observed_payloads != expected_payloads:
                raise HTTPException(status_code=409, detail="One or both conflicting rows are no longer present; refusing stale resolution.")

            # Resolving a collision may delete the losing row (or replace the
            # winning row in place). Until dependent-row semantics are defined,
            # reject any case where a declared FK currently points at either
            # participant rather than risk an implicit cascade/orphan change.
            for schema in schemas:
                table_names = [row[0] for row in conn.execute(
                    f"SELECT name FROM {schema}.sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name <> '_ss_change_log'"
                )]
                for child_table in table_names:
                    foreign_keys = conn.execute(
                        f"PRAGMA {schema}.foreign_key_list({quote(child_table)})"
                    ).fetchall()
                    for fk in foreign_keys:
                        if str(fk[2]).lower() != table.lower():
                            continue
                        source_col, target_col = fk[3], fk[4] or pk
                        target_values = list(dict.fromkeys(
                            payload[target_col] for payload in allowed if target_col in payload
                        ))
                        if not target_values:
                            continue
                        placeholders = ", ".join("?" for _ in target_values)
                        reference = conn.execute(
                            f"SELECT 1 FROM {schema}.{quote(child_table)} "
                            f"WHERE {quote(source_col)} IN ({placeholders}) LIMIT 1",
                            target_values,
                        ).fetchone()
                        if reference:
                            raise HTTPException(
                                status_code=409,
                                detail=f"Cannot resolve INSERT collision while '{child_table}.{source_col}' references a participant row.",
                            )

            source_sequence = max(int(conn.execute(
                f"SELECT COALESCE(MAX(source_sequence),0) FROM ("
                f"SELECT source_sequence FROM {schema}._ss_change_log WHERE source_id=? UNION ALL "
                f"SELECT source_sequence FROM {schema}._ss_compacted_receipts WHERE source_id=?)",
                (source_id, source_id)
            ).fetchone()[0]) for schema in schemas) + 1
            now = datetime.now(timezone.utc).isoformat()
            old_snapshots = {
                replica_a_id: {str(row_id): read_row("main", row_id) for row_id in participant_ids},
                replica_b_id: {str(row_id): read_row("replica_b", row_id) for row_id in participant_ids},
            }
            for schema in schemas:
                for row_id in participant_ids:
                    conn.execute(f"DELETE FROM {schema}.{quote(table)} WHERE {quote(pk)}=?", (row_id,))
                    if read_row(schema, row_id) is not None:
                        raise HTTPException(status_code=409, detail=f"Could not remove conflict row {row_id!r} from {schema}.")
                columns = list(resolved_value)
                conn.execute(
                    f"INSERT INTO {schema}.{quote(table)} ({', '.join(quote(c) for c in columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    [resolved_value[c] for c in columns],
                )
                if read_row(schema, resolved_value[pk]) != resolved_value:
                    raise HTTPException(status_code=409, detail=f"Resolved payload did not persist completely in {schema}.")

            operation_payload = {"kind": "insert_collision_resolution", "value": resolved_value,
                                 "removed_primary_keys": participant_ids, "conflict_id": conflict_id}
            for schema, replica_id in zip(schemas, (replica_a_id, replica_b_id)):
                seq = conn.execute(
                    f"SELECT COALESCE(MAX(sequence),0)+1 FROM ("
                    f"SELECT sequence FROM {schema}._ss_change_log UNION ALL "
                    f"SELECT sequence FROM {schema}._ss_compacted_receipts)"
                ).fetchone()[0]
                conn.execute(
                    f"INSERT INTO {schema}._ss_change_log "
                    "(id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,applied_at,op_type,origin_id,sequence,source_id,source_sequence,depends_on) "
                    "VALUES (?,?,?,?,?,?,?,0,?,?, 'RESOLVE',?,?,?,?,?)",
                    (str(uuid.uuid4()), table, str(resolved_value[pk]), "*", json.dumps(old_snapshots, default=str),
                     json.dumps(operation_payload, sort_keys=True, default=str), time.time(), replica_id, now,
                     operation_id, seq, source_id, source_sequence, "[]"),
                )
            conn.commit()
            return {"operation_id": operation_id, "source_id": source_id, "source_sequence": source_sequence, "replayed": False}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"INSERT collision resolution rolled back: {exc}") from exc


@router.post("/conflicts/detect", status_code=200)
def detect_conflicts(body: ConflictDetectRequest, response: Response) -> list[dict[str, Any]]:
    """
    Run three-way diff between replica A, replica B, and base database.
    Persists detected conflicts into the conflict store.
    """
    db_info = app_state.get_db(body.db_id)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Database '{body.db_id}' not found.")

    base_path = db_info["path"]
    rep_a_path = app_state.get_replica_path(body.replica_a_id)
    rep_b_path = app_state.get_replica_path(body.replica_b_id)

    if not rep_a_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_a_id}' not found.")
    if not rep_b_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_b_id}' not found.")

    detect_result = _detector.detect(
        replica_a_db=rep_a_path,
        replica_b_db=rep_b_path,
        base_db=base_path,
        replica_a_id=body.replica_a_id,
        replica_b_id=body.replica_b_id,
    )
    # Keep the existing list response while making unsupported tables visible
    # to API clients without misinterpreting DetectResult as a plain list.
    response.headers["X-SemanticSync-Skipped-Tables"] = ",".join(detect_result.skipped_tables)

    records = []
    for c in detect_result.conflicts:
        rec = {
            "conflict_id": c.conflict_id,
            "db_id": body.db_id,
            "table": c.table,
            "row_id": c.row_id,
            "column": c.column,
            "conflict_type": getattr(c, "conflict_type", "UPDATE_UPDATE"),
            "base_value": c.base_value,
            "value_a": c.replica_a_value,
            "value_b": c.replica_b_value,
            "replica_a_id": c.replica_a_id,
            "replica_b_id": c.replica_b_id,
            "replica_a_ts": c.replica_a_ts,
            "replica_b_ts": c.replica_b_ts,
            "status": getattr(c, "status", "pending"),
            "explanation": getattr(c, "explanation", None),
            "detected_at": c.detected_at,
            "policy": app_state.get_policy(body.db_id, c.table, c.column) or "REJECT",
        }
        _manager.add_conflict(rec)
        records.append(rec)

    return records


@router.post("/conflicts/resolve", status_code=200)
@serialized_mutation
def resolve_conflict(body: ConflictResolveRequest) -> dict[str, Any]:
    """
    Resolve a specific conflict.
    resolution_mode: 'auto', 'pick_a', 'pick_b', 'custom'
    """
    record = app_state.get_conflict(body.conflict_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Conflict '{body.conflict_id}' not found.")

    mode = body.resolution_mode.strip().lower()

    if mode == "pick_a":
        resolved_value = record.get("value_a")
        status = "resolved"
        explanation = f"Manual resolution: picked Replica A value ({resolved_value!r})"
    elif mode == "pick_b":
        resolved_value = record.get("value_b")
        status = "resolved"
        explanation = f"Manual resolution: picked Replica B value ({resolved_value!r})"
    elif mode == "custom":
        resolved_value = body.custom_value
        status = "resolved"
        explanation = f"Manual resolution: custom value applied ({resolved_value!r})"
    elif mode == "auto":
        if record.get("conflict_type") in ("INSERT_INSERT", "UNIQUE_COLLISION"):
            raise HTTPException(status_code=400, detail="INSERT collisions require explicit pick_a, pick_b, or custom resolution.")
        db_id = record.get("db_id")
        table = record.get("table")
        column = record.get("column")
        policy = app_state.get_policy(db_id, table, column) if db_id else record.get("policy", "REJECT")
        if not policy:
            policy = record.get("policy", "REJECT")

        bounded_bounds = None
        resolver_policy = policy
        if policy and policy_base_name(policy) == "BOUNDED_SUM":
            try:
                bounded_bounds = parse_bounded_sum_bounds(policy)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            resolver_policy = "BOUNDED_SUM"

        try:
            res = SemanticResolver.resolve(
                policy=resolver_policy,
                base_value=record.get("base_value"),
                replica_a_value=record.get("value_a"),
                replica_b_value=record.get("value_b"),
                replica_a_id=record.get("replica_a_id", "replica_a"),
                replica_b_id=record.get("replica_b_id", "replica_b"),
                replica_a_ts=record.get("replica_a_ts"),
                replica_b_ts=record.get("replica_b_ts"),
                min_bound=bounded_bounds[0] if bounded_bounds else None,
                max_bound=bounded_bounds[1] if bounded_bounds else None,
            )
            resolved_value = res.resolved_value
            status = res.status
            explanation = res.explanation
        except ResolutionError as e:
            raise HTTPException(status_code=400, detail=f"Policy resolution failed: {e}")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution_mode '{mode}'. Must be one of: 'auto', 'pick_a', 'pick_b', 'custom'",
        )

    # Write-back only after both replicas are available. A row-level None is
    # an explicit delete resolution; a cell-level None remains a NULL value.
    if status == "resolved":
        table_name = record["table"]
        col_name = record["column"]
        row_id = record["row_id"]
        replica_a_id = record.get("replica_a_id")
        replica_b_id = record.get("replica_b_id")
        replica_a_path = app_state.get_replica_path(replica_a_id) if replica_a_id else None
        replica_b_path = app_state.get_replica_path(replica_b_id) if replica_b_id else None
        if not replica_a_path or not replica_b_path:
            raise HTTPException(status_code=409, detail="Both replicas must be available to resolve this conflict.")
        if record.get("conflict_type") in ("INSERT_INSERT", "UNIQUE_COLLISION"):
            if not isinstance(resolved_value, dict):
                raise HTTPException(status_code=400, detail="INSERT collision resolution must be a complete row payload.")
            audit = _write_insert_collision_atomically(
                replica_a_path, replica_b_path, record, resolved_value,
                replica_a_id, replica_b_id,
            )
            record["resolution_operation"] = audit
        else:
            pol = app_state.get_policy(record.get("db_id"), table_name, col_name) if record.get("db_id") else record.get("policy")
            write_bounds = None
            if pol and policy_base_name(pol) == "BOUNDED_SUM":
                try:
                    write_bounds = parse_bounded_sum_bounds(pol)
                except ValueError:
                    write_bounds = None

            _write_resolution_atomically(
                replica_a_path, replica_b_path, table_name, row_id, col_name, resolved_value,
                replica_a_id, replica_b_id,
                bounded_bounds=write_bounds,
            )

    updated_record = dict(record)
    updated_record["status"] = status
    updated_record["resolved_value"] = resolved_value
    updated_record["resolution_mode"] = mode
    updated_record["explanation"] = explanation
    updated_record["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    app_state.store_conflict(body.conflict_id, updated_record)
    _manager.apply_resolution(body.conflict_id, updated_record)

    return {
        "status": status,
        "result": resolved_value,
        "policy": record.get("policy"),
        "explanation": explanation,
        "conflict": updated_record,
    }


@router.get("/conflicts", status_code=200)
def list_conflicts(
    status: Optional[str] = Query(None, description="Filter by pending, resolved, flagged"),
    db_id: Optional[str] = Query(None, description="Filter by db_id"),
) -> list[dict[str, Any]]:
    """List detected conflicts."""
    all_conflicts = list(app_state.conflicts.values())
    if db_id:
        all_conflicts = [c for c in all_conflicts if c.get("db_id") == db_id]
    if status and status != "all":
        all_conflicts = [c for c in all_conflicts if c.get("status") == status]
    return all_conflicts


@router.get("/conflicts/{conflict_id}", status_code=200)
def get_conflict(conflict_id: str) -> dict[str, Any]:
    """Get single conflict record."""
    c = app_state.get_conflict(conflict_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Conflict '{conflict_id}' not found.")
    return c
