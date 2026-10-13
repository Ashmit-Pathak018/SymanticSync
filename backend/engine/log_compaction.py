"""Conservative per-database change-log compaction primitives.

Acknowledgements are exact operation identities. HLC is only a strict cutoff
after every enrolled replica has acknowledged the operation; it is never used
as a substitute for delivery evidence.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from backend.engine.fk_quarantine import connect_with_foreign_keys
from backend.engine.mutation_lock import serialized_mutation


def ensure_compaction_tables(conn: sqlite3.Connection, schema: str = "main") -> None:
    if schema not in {"main", "replica_b"}:
        raise ValueError(f"Unsupported SQLite schema: {schema}")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {schema}._ss_compacted_receipts (
        origin_id TEXT PRIMARY KEY, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
        column_name TEXT NOT NULL, op_type TEXT NOT NULL, source_id TEXT,
        source_sequence INTEGER, sequence INTEGER, replica_id TEXT NOT NULL,
        ts_pt REAL NOT NULL, ts_l INTEGER NOT NULL,
        depends_on TEXT NOT NULL DEFAULT '[]', payload_hash TEXT NOT NULL,
        bounded_delta NUMERIC, bounds_min NUMERIC, bounds_max NUMERIC,
        compacted_at TEXT NOT NULL
    )""")


def ensure_checkpoint_metadata(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS _ss_checkpoint_metadata (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        checkpoint_id TEXT NOT NULL,
        manifest_hash TEXT NOT NULL
    )""")


def operation_payload_hash(
    old_value: Any, new_value: Any, table_name: str, row_id: Any,
    column_name: str, op_type: str, source_id: str | None,
    source_sequence: int | None, depends_on: str | None,
    bounded_delta: Any = None, bounds_min: Any = None, bounds_max: Any = None,
) -> str:
    payload = [old_value, new_value, table_name, str(row_id), column_name, op_type,
               source_id, source_sequence, depends_on or "[]", bounded_delta,
               bounds_min, bounds_max]
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()


def compactable_operation_ids(
    replica_acknowledgements: dict[str, dict[str, dict[str, Any]]],
) -> tuple[set[str], tuple[float, int] | None]:
    """Return exact IDs acknowledged by every replica and their scalar horizon.

    Per-replica maps are keyed by operation ID. A missing replica or empty
    vector returns no horizon; source sequences are never compared across
    different sources.
    """
    if not replica_acknowledgements or any(not vector for vector in replica_acknowledgements.values()):
        return set(), None
    id_sets = [set(vector) for vector in replica_acknowledgements.values()]
    common = set.intersection(*id_sets)
    common = {
        operation_id for operation_id in common
        if len({vector[operation_id].get("payload_hash") for vector in replica_acknowledgements.values()}) == 1
        and next(iter(replica_acknowledgements.values()))[operation_id].get("payload_hash") is not None
    }
    if not common:
        return set(), None
    # The scalar horizon is only a cutoff. Exact-ID intersection below
    # independently proves each candidate was observed by every participant.
    frontiers = []
    for vector in replica_acknowledgements.values():
        stamps = [(float(v["ts_pt"]), int(v["ts_l"])) for v in vector.values()]
        frontiers.append(max(stamps))
    return common, min(frontiers)


@serialized_mutation
def compact_change_log(
    db_path: str, enrolled_replicas: list[str], *, all_acknowledged_ids: set[str],
    stable_horizon: tuple[float, int] | None,
    acknowledged_payload_hashes: dict[str, str] | None = None,
    checkpoint_id: str | None = None,
    manifest_hash: str | None = None,
    expected_parent_checkpoint_id: str | None = None,
) -> dict[str, Any]:
    """Move only globally acknowledged, dependency-closed entries below horizon.

    The receipt ledger keeps operation identity after pruning, preventing a
    stale duplicate from being applied again. Missing membership/ACK evidence
    produces no pruning. This is a local SQLite transaction and restart-safe.
    """
    if not enrolled_replicas or stable_horizon is None:
        return {"pruned": 0, "stable_horizon": None, "reason": "missing replica acknowledgement"}
    from datetime import datetime, timezone

    with connect_with_foreign_keys(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            ensure_compaction_tables(conn)
            if checkpoint_id:
                ensure_checkpoint_metadata(conn)
                previous = conn.execute("SELECT checkpoint_id,manifest_hash FROM _ss_checkpoint_metadata WHERE singleton=1").fetchone()
                if previous and previous[0] == checkpoint_id and previous[1] != manifest_hash:
                    raise RuntimeError("Checkpoint identity was reused with a different manifest.")
                if previous and previous[0] != checkpoint_id and expected_parent_checkpoint_id != previous[0]:
                    raise RuntimeError("Replica checkpoint lineage does not match recovery manifest.")
                if not previous and expected_parent_checkpoint_id is not None:
                    raise RuntimeError("Replica checkpoint lineage metadata is missing.")
            cols = {r[1] for r in conn.execute("PRAGMA table_info('_ss_change_log')")}
            required = {"origin_id", "source_id", "source_sequence", "ts_pt", "ts_l", "depends_on"}
            if not required <= cols:
                conn.rollback()
                return {"pruned": 0, "stable_horizon": stable_horizon, "reason": "legacy log lacks causal metadata"}
            rows = conn.execute("""SELECT id,table_name,row_id,column_name,old_value,new_value,
                ts_pt,ts_l,replica_id,applied_at,op_type,origin_id,sequence,source_id,
                source_sequence,depends_on,bounded_delta,bounds_min,bounds_max
                FROM _ss_change_log""").fetchall()
            known = set(all_acknowledged_ids)
            candidates = {}
            origin_counts: dict[str, int] = {}
            for row in rows:
                oid = str(row[11] or row[0] or "")
                origin_counts[oid] = origin_counts.get(oid, 0) + 1
                stamp = (float(row[6]), int(row[7]))
                payload_hash = operation_payload_hash(
                    row[4], row[5], row[1], row[2], row[3], row[10], row[13],
                    row[14], row[15], row[16], row[17], row[18],
                )
                hash_matches = (
                    acknowledged_payload_hashes is None
                    or acknowledged_payload_hashes.get(oid) == payload_hash
                )
                if oid and oid in known and hash_matches and stamp < stable_horizon:
                    candidates[oid] = row
            # Keep causal ancestors unless those identities are also in the
            # exact all-replica acknowledgement set and below the horizon.
            safe = {oid for oid in candidates if origin_counts.get(oid) == 1}
            changed = True
            while changed:
                changed = False
                for oid in tuple(safe):
                    try:
                        deps = json.loads(candidates[oid][15] or "[]")
                    except (TypeError, ValueError):
                        deps = ["invalid-dependency-metadata"]
                    if any(dep not in safe and conn.execute(
                        "SELECT 1 FROM _ss_compacted_receipts WHERE origin_id=?", (dep,)
                    ).fetchone() is None for dep in deps):
                        safe.remove(oid)
                        changed = True
            now = datetime.now(timezone.utc).isoformat()
            for oid in sorted(safe):
                row = candidates[oid]
                payload_hash = operation_payload_hash(
                    row[4], row[5], row[1], row[2], row[3], row[10], row[13],
                    row[14], row[15], row[16], row[17], row[18],
                )
                conn.execute("""INSERT OR IGNORE INTO _ss_compacted_receipts
                    (origin_id,table_name,row_id,column_name,op_type,source_id,
                     source_sequence,sequence,replica_id,ts_pt,ts_l,depends_on,payload_hash,
                     bounded_delta,bounds_min,bounds_max,compacted_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (oid, row[1], row[2], row[3], row[10], row[13], row[14],
                     row[12], row[8], row[6], row[7], row[15], payload_hash,
                     row[16], row[17], row[18], now))
                stored = conn.execute(
                    "SELECT table_name,row_id,column_name,op_type,source_id,source_sequence,"
                    "sequence,replica_id,ts_pt,ts_l,depends_on,payload_hash,bounded_delta,bounds_min,bounds_max "
                    "FROM _ss_compacted_receipts WHERE origin_id=?", (oid,),
                ).fetchone()
                expected = (row[1], row[2], row[3], row[10], row[13], row[14],
                            row[12], row[8], row[6], row[7], row[15], payload_hash,
                            row[16], row[17], row[18])
                if not stored or tuple(stored) != expected:
                    raise RuntimeError(f"Compacted receipt metadata mismatch for operation {oid}.")
                deleted = conn.execute(
                    "DELETE FROM _ss_change_log WHERE COALESCE(origin_id,id)=?", (oid,)
                ).rowcount
                if deleted != 1:
                    raise RuntimeError(f"Expected one log row for operation {oid}; deleted {deleted}.")
            if checkpoint_id:
                conn.execute("INSERT INTO _ss_checkpoint_metadata(singleton,checkpoint_id,manifest_hash) VALUES(1,?,?) "
                             "ON CONFLICT(singleton) DO UPDATE SET checkpoint_id=excluded.checkpoint_id,manifest_hash=excluded.manifest_hash",
                             (checkpoint_id, manifest_hash or ""))
            conn.commit()
            return {"pruned": len(safe), "stable_horizon": stable_horizon,
                    "enrolled_replicas": list(enrolled_replicas),
                    "retained": len(rows) - len(safe)}
        except Exception:
            conn.rollback()
            raise
