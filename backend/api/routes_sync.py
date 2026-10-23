"""
backend/api/routes_sync.py
───────────────────────────
Replica synchronization triggers, simulation, and status.

Endpoints
---------
GET  /api/v1/sync/status             → Synchronization status and counts
POST /api/v1/sync/run                → Execute replica sync pipeline
POST /api/v1/sync/generate-conflict  → Inject controlled divergent edit across replicas
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictFloat, StrictInt

from backend.api.models import SyncRequest
from backend.api.state import DATA_DIR, app_state
from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.policy_registry import policy_base_name, parse_bounded_sum_bounds
from backend.engine.fk_quarantine import connect_with_foreign_keys
from backend.engine.log_compaction import compact_change_log, compactable_operation_ids, operation_payload_hash
from backend.engine.checkpoint_store import (
    CheckpointStoreBlocked, checkpoint_state, create_database_snapshot, initialize_checkpoint_store,
    latest_completed_checkpoint,
    list_recoverable_checkpoints, set_checkpoint_state, validate_checkpoint_store,
    write_checkpoint_record,
)
from backend.engine.mutation_lock import serialized_mutation
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

router = APIRouter(tags=["Sync"])
_sync_engine = CRDTSyncEngine()


class ConflictGenerateRequest(BaseModel):
    db_id: str
    replica_a_id: str
    replica_b_id: str
    table: str
    row_id: Any
    column: str
    value_a: Any
    value_b: Any


class IncrementRequest(BaseModel):
    db_id: str
    replica_id: str
    table: str
    row_id: Any
    column: str
    delta: StrictInt | StrictFloat


@router.get("/sync/status", status_code=200)
def sync_status() -> dict[str, Any]:
    """Return synchronization overview and pending conflict stats."""
    conflicts = list(app_state.conflicts.values())
    pending = [c for c in conflicts if c.get("status") == "pending"]
    flagged = [c for c in conflicts if c.get("status") == "flagged"]
    resolved = [c for c in conflicts if c.get("status") == "resolved"]

    return {
        "status": "ready",
        "registered_databases": len(app_state.databases),
        "registered_replicas": len(app_state.replicas),
        "total_conflicts": len(conflicts),
        "pending_conflicts": len(pending),
        "flagged_conflicts": len(flagged),
        "resolved_conflicts": len(resolved),
        "checkpoint_store": _checkpoint_store_status(),
        "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.post("/sync/run", status_code=200)
@serialized_mutation
def run_sync(body: SyncRequest) -> dict[str, Any]:
    """
    Execute three-way synchronization between replica A and replica B against their base database.
    Applies schema policies to resolve divergent updates deterministically.
    """
    store_status = _checkpoint_store_status()
    if store_status["status"] == "blocked":
        raise HTTPException(status_code=409, detail={"status": "blocked", "reason": store_status["reason"]})
    blocked_checkpoints: list[dict[str, str]] = []
    if store_status["status"] == "ready":
        try:
            recoverable = list_recoverable_checkpoints(_checkpoint_store_path())
            for checkpoint in recoverable:
                try:
                    _resume_checkpoint(checkpoint)
                except Exception as exc:
                    blocked = {"checkpoint_id": checkpoint.get("checkpoint_id", "unknown"),
                               "db_id": checkpoint.get("manifest", {}).get("db_id", ""),
                               "reason": str(exc)}
                    blocked_checkpoints.append(blocked)
                    if blocked["db_id"] == body.db_id:
                        raise HTTPException(status_code=409, detail={
                            "status": "blocked", "reason": blocked["reason"],
                            "checkpoint_id": blocked["checkpoint_id"],
                        }) from exc
            latest = latest_completed_checkpoint(_checkpoint_store_path(), body.db_id)
            if latest:
                expected = latest["checkpoint_id"]
                for member in latest["manifest"].get("replicas", []):
                    current = app_state.get_replica(member["replica_id"])
                    if not current or current.get("db_path") != member.get("db_path") or current.get("incarnation_id") != member.get("incarnation_id"):
                        raise CheckpointStoreBlocked(f"registry membership differs from completed checkpoint for {member['replica_id']}")
                for replica in app_state.list_replicas_for_db(body.db_id):
                    if _replica_checkpoint_id(replica["db_path"]) != expected:
                        raise CheckpointStoreBlocked(
                            f"replica {replica['replica_id']} is behind checkpoint {expected}; preserve and reseed its local changes before sync"
                        )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=409, detail={"status": "blocked", "reason": str(exc)}) from exc
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

    # Retrieve policies formatted as {table: {column: policy}}
    assigned_policies = app_state.get_policies_for_db(body.db_id)
    nested_policies: dict[str, dict[str, str]] = {}
    for key, pol in assigned_policies.items():
        # key format is "table:column"
        parts = key.split(":")
        if len(parts) == 2:
            tbl, col = parts
            nested_policies.setdefault(tbl, {})[col] = pol

    # Set table-level tombstone policy if provided
    tombstone_pol = getattr(body, "tombstone_policy", "FLAG_FOR_REVIEW") or "FLAG_FOR_REVIEW"
    for tbl in list(nested_policies.keys()):
        nested_policies[tbl]["__tombstone__"] = tombstone_pol

    result = _sync_engine.sync_replicas(
        replica_a_path=rep_a_path,
        replica_b_path=rep_b_path,
        base_path=base_path,
        replica_a_id=body.replica_a_id,
        replica_b_id=body.replica_b_id,
        policies=nested_policies,
    )

    # Persist only operations present in each replica's durable log after the
    # sync transaction. Exact operation IDs, not wall-clock progress alone,
    # determine the common acknowledgement set used by compaction.
    for replica_id, replica_path in ((body.replica_a_id, rep_a_path), (body.replica_b_id, rep_b_path)):
        with connect_with_foreign_keys(replica_path) as conn:
            has_log = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_change_log'"
            ).fetchone()
            rows = conn.execute(
                "SELECT COALESCE(origin_id,id),COALESCE(source_id,replica_id),"
                "COALESCE(source_sequence,sequence),ts_pt,ts_l,old_value,new_value,"
                "table_name,row_id,column_name,op_type,depends_on,bounded_delta,bounds_min,bounds_max "
                "FROM _ss_change_log"
            ).fetchall() if has_log else []
        app_state.record_replica_acknowledgements(body.db_id, replica_id, [
            {"operation_id": row[0], "source_id": row[1], "source_sequence": row[2],
             "ts_pt": row[3], "ts_l": row[4],
             "payload_hash": operation_payload_hash(
                 row[5], row[6], row[7], row[8], row[9], row[10], row[1], row[2],
                 row[11], row[12], row[13], row[14],
             )} for row in rows
            if row[0] is not None and row[2] is not None
        ])
    received_acknowledgements: dict[str, list[dict]] = {}
    for acknowledgement in result.acknowledgements:
        received_acknowledgements.setdefault(acknowledgement["replica_id"], []).append(acknowledgement)
    for replica_id, operations in received_acknowledgements.items():
        app_state.record_replica_acknowledgements(body.db_id, replica_id, operations)

    # Sync any newly generated conflicts with app_state
    for change in result.applied_changes:
        cid = change.get("conflict_id")
        if cid:
            rec = app_state.get_conflict(cid) or {}
            rec.update(
                {
                    "conflict_id": cid,
                    "db_id": body.db_id,
                    "table": change.get("table"),
                    "row_id": change.get("row_id"),
                    "column": change.get("column"),
                    "status": "resolved",
                    "resolved_value": change.get("resolved_value"),
                    "policy": change.get("policy"),
                    "explanation": change.get("explanation"),
                    "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            app_state.store_conflict(cid, rec)

    return {
        "status": "completed",
        "total_conflicts": result.total_conflicts,
        "auto_resolved": result.auto_resolved,
        "flagged_for_review": result.flagged_for_review,
        "applied_changes": result.applied_changes,
        "flagged_conflicts": result.flagged_conflicts,
        "duration_ms": round(result.duration_ms, 2),
        "skipped_tables": result.skipped_tables,
        "rejected_operations": result.rejected_operations,
        "blocked_checkpoints": blocked_checkpoints,
    }


def _checkpoint_store_path():
    return DATA_DIR / "checkpoint_store.sqlite"


def _prior_checkpoint_evidence() -> str | None:
    for replica in app_state.replicas.values():
        db_path = replica.get("db_path")
        if not db_path or not Path(db_path).exists():
            return f"registered replica database is missing: {replica.get('replica_id')}"
        try:
            with sqlite3.connect(db_path) as conn:
                receipt_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_compacted_receipts'").fetchone()
                if receipt_table and conn.execute("SELECT 1 FROM _ss_compacted_receipts LIMIT 1").fetchone():
                    return f"compacted operation receipts exist without a trusted checkpoint store: {replica.get('replica_id')}"
                marker_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_checkpoint_metadata'").fetchone()
                if marker_table and conn.execute("SELECT 1 FROM _ss_checkpoint_metadata LIMIT 1").fetchone():
                    return f"replica checkpoint marker exists without a trusted checkpoint store: {replica.get('replica_id')}"
        except sqlite3.DatabaseError:
            return f"cannot validate registered replica database: {replica.get('replica_id')}"
    return None


def _checkpoint_store_status() -> dict[str, Any]:
    path = _checkpoint_store_path()
    if app_state.registry_load_error:
        return {"status": "blocked", "reason": app_state.registry_load_error}
    if not path.exists():
        if app_state.checkpoint_store_id:
            return {"status": "blocked", "reason": "checkpoint store is missing; pruning is blocked"}
        evidence = _prior_checkpoint_evidence()
        if evidence:
            return {"status": "blocked", "reason": evidence}
        return {"status": "uninitialized", "reason": "explicit checkpoint-store initialization required"}
    try:
        info = validate_checkpoint_store(path, expected_store_id=app_state.checkpoint_store_id)
        if app_state.checkpoint_store_id is None:
            if info["checkpoints"]:
                if info.get("manifest_store_ids") == [info["store_id"]]:
                    for manifest in info.get("manifests", []):
                        for member in manifest.get("replicas", []):
                            current = app_state.get_replica(member["replica_id"])
                            if not current or current.get("db_path") != member.get("db_path") or current.get("incarnation_id") != member.get("incarnation_id"):
                                return {"status": "blocked", "reason": f"registry membership cannot be reconciled for {member['replica_id']}"}
                    try:
                        app_state.set_checkpoint_store_id(info["store_id"])
                    except Exception as exc:
                        return {"status": "blocked", "reason": f"registry identity reconciliation failed: {exc}"}
                else:
                    return {"status": "blocked", "reason": "checkpoint history exists without a verifiable registry identity"}
            else:
                evidence = _prior_checkpoint_evidence()
                if evidence:
                    return {"status": "blocked", "reason": evidence}
                return {"status": "uninitialized", "reason": "explicit checkpoint-store adoption required"}
        return info
    except CheckpointStoreBlocked as exc:
        return {"status": "blocked", "reason": str(exc)}


@router.post("/sync/checkpoint-store/initialize", status_code=200)
@serialized_mutation
def initialize_sync_checkpoint_store() -> dict[str, Any]:
    """Explicitly provision the checkpoint journal; startup never recreates it."""
    if app_state.registry_load_error:
        return {"status": "blocked", "reason": app_state.registry_load_error}
    path = _checkpoint_store_path()
    if path.exists():
        try:
            info = validate_checkpoint_store(path)
            if app_state.checkpoint_store_id not in (None, info["store_id"]):
                return {"status": "blocked", "reason": "registry/store identity mismatch"}
            if app_state.checkpoint_store_id is None and info["checkpoints"]:
                return {"status": "blocked", "reason": "existing checkpoint history has no registry identity"}
            app_state.set_checkpoint_store_id(info["store_id"])
            return {"status": "ready", "store_id": info["store_id"], "adopted": True}
        except CheckpointStoreBlocked as exc:
            return {"status": "blocked", "reason": str(exc)}
    # Never initialize over evidence of prior compaction or an unreadable member.
    evidence = _prior_checkpoint_evidence()
    if evidence:
        return {"status": "blocked", "reason": evidence}
    try:
        store_id = initialize_checkpoint_store(path)
        app_state.set_checkpoint_store_id(store_id)
        return {"status": "ready", "store_id": store_id, "adopted": False}
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)}


def _verify_replica_history(db_path: str, op_hashes: dict[str, str]) -> None:
    with connect_with_foreign_keys(db_path) as conn:
        for operation_id, expected_hash in op_hashes.items():
            log = conn.execute("SELECT old_value,new_value,table_name,row_id,column_name,op_type,source_id,source_sequence,depends_on,bounded_delta,bounds_min,bounds_max FROM _ss_change_log WHERE COALESCE(origin_id,id)=?", (operation_id,)).fetchone()
            receipt = conn.execute("SELECT payload_hash FROM _ss_compacted_receipts WHERE origin_id=?", (operation_id,)).fetchone()
            if log:
                actual = operation_payload_hash(*log[:6], log[6], log[7], log[8], log[9], log[10], log[11])
                if actual != expected_hash:
                    raise CheckpointStoreBlocked(f"operation history hash mismatch on {db_path}: {operation_id}")
            elif not receipt or receipt[0] != expected_hash:
                raise CheckpointStoreBlocked(f"operation history missing on {db_path}: {operation_id}")


def _replica_checkpoint_id(db_path: str) -> str | None:
    with connect_with_foreign_keys(db_path) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_checkpoint_metadata'").fetchone()
        if not exists:
            return None
        row = conn.execute("SELECT checkpoint_id FROM _ss_checkpoint_metadata WHERE singleton=1").fetchone()
        return str(row[0]) if row else None


def _snapshot_schema_fingerprint(conn: sqlite3.Connection) -> str:
    """Fingerprint the complete user schema in a captured replica snapshot."""
    rows = conn.execute(
        "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND name NOT LIKE '_ss_%' "
        "ORDER BY type,name,tbl_name"
    ).fetchall()
    payload = json.dumps([tuple(row) for row in rows], separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_operation_frontier(conn: sqlite3.Connection) -> dict[str, str]:
    """Return operation identities and payload hashes present in a snapshot."""
    frontier: dict[str, str] = {}
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "_ss_change_log" in tables:
        cols = {row[1] for row in conn.execute('PRAGMA table_info("_ss_change_log")')}
        required = {"id", "origin_id", "old_value", "new_value", "table_name", "row_id",
                    "column_name", "op_type", "source_id", "source_sequence", "depends_on"}
        if not required <= cols:
            raise CheckpointStoreBlocked("snapshot change log lacks operation identity metadata")
        optional = ("bounded_delta", "bounds_min", "bounds_max")
        select_optional = [name if name in cols else f"NULL AS {name}"
                           for name in optional]
        rows = conn.execute(
            "SELECT id,origin_id,old_value,new_value,table_name,row_id,column_name,op_type,"
            "source_id,source_sequence,depends_on," + ",".join(select_optional) +
            " FROM _ss_change_log"
        ).fetchall()
        for row in rows:
            operation_id = str(row[1] or row[0])
            digest = operation_payload_hash(
                row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
                row[10], row[11], row[12], row[13],
            )
            if operation_id in frontier and frontier[operation_id] != digest:
                raise CheckpointStoreBlocked(f"snapshot has conflicting operation identity: {operation_id}")
            frontier[operation_id] = digest
    if "_ss_compacted_receipts" in tables:
        rows = conn.execute("SELECT origin_id,payload_hash FROM _ss_compacted_receipts").fetchall()
        for operation_id, digest in rows:
            operation_id, digest = str(operation_id), str(digest)
            if operation_id in frontier and frontier[operation_id] != digest:
                raise CheckpointStoreBlocked(f"snapshot log/receipt frontier conflicts: {operation_id}")
            frontier[operation_id] = digest
    return dict(sorted(frontier.items()))


def _snapshot_data_fingerprint(conn: sqlite3.Connection) -> str:
    """Hash user-table rows independent of row-return order and SQLite internals."""
    digest = hashlib.sha256()
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_ss_%' ORDER BY name"
    )]
    for table in tables:
        digest.update(json.dumps([table], separators=(",", ":")).encode("utf-8"))
        escaped = table.replace('"', '""')
        rows = conn.execute(f'SELECT * FROM "{escaped}"').fetchall()
        encoded_rows = []
        for row in rows:
            encoded = []
            for value in row:
                if isinstance(value, bytes):
                    encoded.append(["bytes", value.hex()])
                elif value is None:
                    encoded.append(["null", None])
                else:
                    encoded.append([type(value).__name__, value])
            encoded_rows.append(json.dumps(encoded, separators=(",", ":"), default=str))
        for encoded in sorted(encoded_rows):
            digest.update(encoded.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _snapshot_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: snapshot[key] for key in (
        "checkpoint_id", "replica_id", "replica_db_path", "incarnation_id",
        "membership_epoch", "schema_fingerprint", "operation_frontier", "data_fingerprint",
    )}


def _validate_snapshot_identity(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_checkpoint_snapshot_identity'"
    ).fetchone()
    if not table:
        raise CheckpointStoreBlocked(f"checkpoint snapshot identity is missing: {snapshot.get('replica_id')}")
    row = conn.execute("SELECT identity_json FROM _ss_checkpoint_snapshot_identity WHERE singleton=1").fetchone()
    expected = json.dumps(_snapshot_identity(snapshot), sort_keys=True, separators=(",", ":"), default=str)
    if not row or row[0] != expected:
        raise CheckpointStoreBlocked(f"checkpoint snapshot identity mismatch: {snapshot.get('replica_id')}")


def _validate_manifest_snapshots(manifest: dict[str, Any], epoch: str) -> None:
    """Validate snapshot/member bijection and recompute all bound metadata."""
    replicas = manifest.get("replicas")
    snapshots = manifest.get("snapshots")
    if not isinstance(replicas, list) or not replicas or not isinstance(snapshots, list):
        raise CheckpointStoreBlocked("checkpoint members or snapshots are missing")
    members: dict[str, dict[str, Any]] = {}
    for member in replicas:
        replica_id = str(member.get("replica_id", ""))
        if not replica_id or replica_id in members:
            raise CheckpointStoreBlocked("checkpoint membership contains missing or duplicate replica IDs")
        members[replica_id] = member
    by_replica: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise CheckpointStoreBlocked("checkpoint snapshot entry is invalid")
        replica_id = str(snapshot.get("replica_id", ""))
        by_replica.setdefault(replica_id, []).append(snapshot)
    if set(by_replica) != set(members) or any(len(items) != 1 for items in by_replica.values()):
        raise CheckpointStoreBlocked("checkpoint snapshots must map one-to-one to replica membership")

    operation_hashes = manifest.get("operation_hashes")
    if not isinstance(operation_hashes, dict):
        raise CheckpointStoreBlocked("checkpoint operation frontier is missing")
    for replica_id, member in members.items():
        snapshot = by_replica[replica_id][0]
        if snapshot.get("replica_db_path") != member.get("db_path"):
            raise CheckpointStoreBlocked(f"checkpoint snapshot database path mismatch: {replica_id}")
        if snapshot.get("incarnation_id") != member.get("incarnation_id"):
            raise CheckpointStoreBlocked(f"checkpoint snapshot incarnation mismatch: {replica_id}")
        if snapshot.get("membership_epoch") != epoch:
            raise CheckpointStoreBlocked(f"checkpoint snapshot membership epoch mismatch: {replica_id}")
        snapshot_path = Path(snapshot.get("path", ""))
        if not snapshot_path.exists() or _sha256_file(snapshot_path) != snapshot.get("sha256"):
            raise CheckpointStoreBlocked(f"checkpoint snapshot missing or corrupt: {replica_id}")
        try:
            with sqlite3.connect(str(snapshot_path)) as snap:
                if snap.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise CheckpointStoreBlocked(f"checkpoint snapshot failed integrity check: {replica_id}")
                _validate_snapshot_identity(snap, snapshot)
                schema_fingerprint = _snapshot_schema_fingerprint(snap)
                frontier = _snapshot_operation_frontier(snap)
                data_fingerprint = _snapshot_data_fingerprint(snap)
        except (sqlite3.DatabaseError, OSError, TypeError, ValueError) as exc:
            raise CheckpointStoreBlocked(f"checkpoint snapshot is unverifiable: {replica_id}: {exc}") from exc
        if snapshot.get("schema_fingerprint") != schema_fingerprint:
            raise CheckpointStoreBlocked(f"checkpoint snapshot schema mismatch: {replica_id}")
        if snapshot.get("operation_frontier") != frontier:
            raise CheckpointStoreBlocked(f"checkpoint snapshot operation frontier mismatch: {replica_id}")
        if snapshot.get("data_fingerprint") != data_fingerprint:
            raise CheckpointStoreBlocked(f"checkpoint snapshot data fingerprint mismatch: {replica_id}")
        if any(frontier.get(operation_id) != digest for operation_id, digest in operation_hashes.items()):
            raise CheckpointStoreBlocked(f"checkpoint snapshot lacks an acknowledged operation: {replica_id}")


def _validate_manifest_frontier(manifest: dict[str, Any]) -> None:
    vectors = manifest.get("acknowledgements")
    operation_hashes = manifest.get("operation_hashes")
    if not isinstance(vectors, dict) or not isinstance(operation_hashes, dict):
        raise CheckpointStoreBlocked("checkpoint acknowledgement frontier is missing or invalid")
    common_ids, horizon = compactable_operation_ids(vectors)
    if common_ids != set(operation_hashes) or horizon is None:
        raise CheckpointStoreBlocked("checkpoint operation IDs do not match the acknowledged frontier")
    if tuple(manifest.get("stable_horizon", ())) != horizon:
        raise CheckpointStoreBlocked("checkpoint stable horizon does not match acknowledgement evidence")
    reference = next(iter(vectors.values()), {})
    if any(operation_hashes.get(operation_id) != reference[operation_id].get("payload_hash")
           for operation_id in common_ids):
        raise CheckpointStoreBlocked("checkpoint operation hashes do not match acknowledgement evidence")


@serialized_mutation
def _resume_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    checkpoint_id = checkpoint["checkpoint_id"]
    manifest = checkpoint["manifest"]
    op_hashes = manifest.get("operation_hashes", {})
    membership = sorted(
        (item["replica_id"], item.get("incarnation_id"), item["db_path"])
        for item in manifest.get("replicas", [])
    )
    epoch = hashlib.sha256(json.dumps(membership, separators=(",", ":")).encode("utf-8")).hexdigest()
    if manifest.get("membership_epoch") != epoch:
        raise CheckpointStoreBlocked("checkpoint membership epoch does not match its member list")
    manifest_member_ids = {item["replica_id"] for item in manifest.get("replicas", [])}
    current_member_ids = {
        item["replica_id"]
        for item in app_state.list_replicas_for_db(manifest.get("db_id", ""))
    }
    if current_member_ids != manifest_member_ids:
        raise CheckpointStoreBlocked(
            "registry membership changed since checkpoint; recovery cannot authorize pruning"
        )
    # Validate all immutable recovery material before ACK reconciliation or pruning.
    _validate_manifest_frontier(manifest)
    _validate_manifest_snapshots(manifest, epoch)
    replicas = manifest.get("replicas", [])
    for replica in replicas:
        current = app_state.get_replica(replica["replica_id"])
        if not current or current.get("db_path") != replica["db_path"] or current.get("incarnation_id") != replica.get("incarnation_id"):
            raise CheckpointStoreBlocked(f"replica membership/path changed since checkpoint: {replica['replica_id']}")
        snapshot = next(item for item in manifest["snapshots"] if item["replica_id"] == replica["replica_id"])
        with sqlite3.connect(current["db_path"]) as replica_conn:
            if _snapshot_schema_fingerprint(replica_conn) != snapshot["schema_fingerprint"]:
                raise CheckpointStoreBlocked(f"replica schema no longer matches checkpoint snapshot: {replica['replica_id']}")
        _validate_post_checkpoint_tail(current["db_path"], snapshot, replica["replica_id"])
        _verify_replica_history(current["db_path"], op_hashes)
    _reconcile_checkpoint_acknowledgements(manifest)
    if checkpoint_state(_checkpoint_store_path(), checkpoint_id) == "COMPLETE":
        if any(_replica_checkpoint_id(replica["db_path"]) != checkpoint_id for replica in replicas):
            raise CheckpointStoreBlocked("completed checkpoint replica marker is missing or inconsistent")
        return {"checkpoint_id": checkpoint_id, "replicas": [], "pruned": 0, "replayed": True}
    set_checkpoint_state(_checkpoint_store_path(), checkpoint_id, "PRUNING")
    results = []
    for replica in replicas:
        result = compact_change_log(
            replica["db_path"], [item["replica_id"] for item in replicas],
            all_acknowledged_ids=set(op_hashes),
            stable_horizon=tuple(manifest["stable_horizon"]),
            acknowledged_payload_hashes=op_hashes,
            checkpoint_id=checkpoint_id,
            manifest_hash=hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest(),
            expected_parent_checkpoint_id=replica.get("parent_checkpoint_id"),
        )
        _verify_replica_history(replica["db_path"], op_hashes)
        results.append(result)
    set_checkpoint_state(_checkpoint_store_path(), checkpoint_id, "COMPLETE")
    return {"checkpoint_id": checkpoint_id, "replicas": results,
            "pruned": sum(item["pruned"] for item in results)}


def _validate_post_checkpoint_tail(db_path: str, snapshot: dict[str, Any], replica_id: str) -> None:
    """Prove that live state is the checkpoint snapshot plus its tracked hot-log tail."""
    snapshot_path = snapshot.get("path")
    if not snapshot_path:
        raise CheckpointStoreBlocked(f"checkpoint snapshot path is missing: {replica_id}")
    with sqlite3.connect(db_path) as live:
        live_frontier = _snapshot_operation_frontier(live)
        live_data = _snapshot_data_fingerprint(live)
        log_cols = {row[1] for row in live.execute('PRAGMA table_info("_ss_change_log")')}
        required = {"id", "origin_id", "sequence", "table_name", "row_id", "column_name",
                    "old_value", "new_value", "op_type", "source_id", "source_sequence",
                    "depends_on", "ts_pt", "ts_l", "bounded_delta", "bounds_min", "bounds_max"}
        if not required <= log_cols:
            raise CheckpointStoreBlocked(f"live operation history is unverifiable: {replica_id}")
        rows = live.execute(
            'SELECT id,origin_id,sequence,table_name,row_id,column_name,old_value,new_value,op_type,'
            'source_id,source_sequence,depends_on,ts_pt,ts_l,bounded_delta,bounds_min,bounds_max '
            'FROM _ss_change_log ORDER BY sequence'
        ).fetchall()
        receipt_ids = {str(row[0]) for row in live.execute(
            'SELECT origin_id FROM _ss_compacted_receipts'
        )} if live.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_compacted_receipts'").fetchone() else set()

    base_frontier = snapshot["operation_frontier"]
    if any(live_frontier.get(operation_id) != digest for operation_id, digest in base_frontier.items()):
        raise CheckpointStoreBlocked(f"checkpoint operation history changed on replica: {replica_id}")
    tail_ids = set(live_frontier) - set(base_frontier)
    if tail_ids & receipt_ids:
        raise CheckpointStoreBlocked(f"post-checkpoint operation was compacted before recovery: {replica_id}")
    by_id: dict[str, tuple[Any, ...]] = {}
    for row in rows:
        operation_id = str(row[1] or row[0])
        if operation_id in tail_ids:
            if operation_id in by_id:
                raise CheckpointStoreBlocked(f"duplicate post-checkpoint operation identity: {operation_id}")
            by_id[operation_id] = row
    if set(by_id) != tail_ids:
        raise CheckpointStoreBlocked(f"post-checkpoint operation payload is missing: {replica_id}")
    if not tail_ids:
        if live_data != snapshot["data_fingerprint"]:
            raise CheckpointStoreBlocked(f"replica data no longer matches checkpoint snapshot: {replica_id}")
        return

    # Replay the local sequence onto a private copy of the validated snapshot.
    # Unsupported operation formats block recovery rather than weakening the
    # snapshot binding or dropping the newer operation.
    expected = sqlite3.connect(":memory:")
    try:
        with sqlite3.connect(snapshot_path) as captured:
            captured.backup(expected)
        sequence_floor = 0
        snapshot_tables = {row[0] for row in expected.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "_ss_change_log" in snapshot_tables:
            sequence_floor = max(sequence_floor, int(expected.execute(
                'SELECT COALESCE(MAX(sequence),0) FROM _ss_change_log'
            ).fetchone()[0] or 0))
        if "_ss_compacted_receipts" in snapshot_tables:
            sequence_floor = max(sequence_floor, int(expected.execute(
                'SELECT COALESCE(MAX(sequence),0) FROM _ss_compacted_receipts'
            ).fetchone()[0] or 0))
        expected.execute("PRAGMA foreign_keys=ON")
        expected.execute("BEGIN IMMEDIATE")
        seen_operations = set(base_frontier)
        seen_sequences: set[int] = set()
        for row in sorted(by_id.values(), key=lambda item: int(item[2])):
            (_, _, _, table, row_id, column, old_value, new_value, op_type, *_rest) = row
            sequence = int(row[2])
            if sequence <= sequence_floor or sequence in seen_sequences:
                raise CheckpointStoreBlocked(f"post-checkpoint sequence metadata is invalid: {replica_id}")
            seen_sequences.add(sequence)
            try:
                dependencies = json.loads(row[11] or "[]")
            except (TypeError, ValueError) as exc:
                raise CheckpointStoreBlocked(f"post-checkpoint dependencies are invalid: {replica_id}") from exc
            if not isinstance(dependencies, list) or any(not isinstance(dep, str) or dep not in seen_operations for dep in dependencies):
                raise CheckpointStoreBlocked(f"post-checkpoint causal dependency is not present: {replica_id}")
            table_q = str(table).replace('"', '""')
            if op_type not in {"UPDATE", "INCREMENT", "INSERT", "DELETE"}:
                raise CheckpointStoreBlocked(
                    f"post-checkpoint {op_type} cannot be safely replay-validated: {replica_id}"
                )
            pk_rows = expected.execute(f'PRAGMA table_info("{table_q}")').fetchall()
            primary = [item[1] for item in sorted((item for item in pk_rows if item[5] > 0), key=lambda item: item[5])]
            if len(primary) != 1:
                raise CheckpointStoreBlocked(f"post-checkpoint operation targets unsupported table: {table}")
            pk_q = primary[0].replace('"', '""')
            columns = [item[1] for item in pk_rows]
            def read_row() -> dict[str, Any] | None:
                cursor = expected.execute(f'SELECT * FROM "{table_q}" WHERE "{pk_q}"=?', (row_id,))
                values = cursor.fetchone()
                return dict(zip([desc[0] for desc in cursor.description], values)) if values is not None else None

            if op_type == "INCREMENT":
                import math
                current_row = read_row()
                if current_row is None or column not in current_row:
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT target is missing: {replica_id}")
                current_value = current_row[column]
                if not isinstance(current_value, (int, float)) or isinstance(current_value, bool):
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT target is not numeric: {replica_id}")
                serialized_current = str(current_value)
                if serialized_current != old_value:
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT precondition mismatch: {replica_id}")
                if row[14] is not None or row[15] is not None or row[16] is not None:
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT has incompatible bounded metadata: {replica_id}")
                try:
                    delta = int(new_value) if isinstance(current_value, int) and new_value is not None and str(new_value).lstrip("+-").isdigit() else float(new_value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT delta is invalid: {replica_id}") from exc
                if isinstance(delta, float) and not math.isfinite(delta):
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT delta is non-finite: {replica_id}")
                candidate = current_value + delta
                if isinstance(candidate, int) and not -(2**63) <= candidate <= 2**63 - 1:
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT overflows SQLite INTEGER: {replica_id}")
                if isinstance(candidate, float) and not math.isfinite(candidate):
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT result is non-finite: {replica_id}")
                col_q = str(column).replace('"', '""')
                changed = expected.execute(
                    f'UPDATE "{table_q}" SET "{col_q}"=? WHERE "{pk_q}"=?',
                    (candidate, row_id),
                )
                stored = read_row()
                if (stored is None or stored.get(column) != candidate
                        or (isinstance(candidate, int) and type(stored.get(column)) is not int)):
                    raise CheckpointStoreBlocked(f"post-checkpoint INCREMENT stored value differs from replay: {replica_id}")
            elif op_type == "UPDATE":
                col_q = str(column).replace('"', '""')
                current = expected.execute(
                    f'SELECT "{col_q}" FROM "{table_q}" WHERE "{pk_q}"=?', (row_id,)
                ).fetchone()
                serialized_current = None if current is None or current[0] is None else str(current[0])
                if current is None or serialized_current != old_value:
                    raise CheckpointStoreBlocked(f"post-checkpoint operation precondition mismatch: {replica_id}")
                changed = expected.execute(
                    f'UPDATE "{table_q}" SET "{col_q}"=? WHERE "{pk_q}"=?', (new_value, row_id)
                )
            elif op_type == "INSERT":
                try:
                    payload = json.loads(new_value)
                except (TypeError, ValueError) as exc:
                    raise CheckpointStoreBlocked(f"post-checkpoint INSERT payload is invalid: {replica_id}") from exc
                if not isinstance(payload, dict) or set(payload) != set(columns) or str(payload.get(primary[0])) != str(row_id):
                    raise CheckpointStoreBlocked(f"post-checkpoint INSERT payload is incomplete: {replica_id}")
                insert_columns = list(payload)
                names = ",".join(f'"{name.replace(chr(34), chr(34)*2)}"' for name in insert_columns)
                placeholders = ",".join("?" for _ in insert_columns)
                changed = expected.execute(
                    f'INSERT INTO "{table_q}" ({names}) VALUES ({placeholders})',
                    [payload[name] for name in insert_columns],
                )
                inserted = read_row()
                if inserted is None or json.dumps(inserted, sort_keys=True, separators=(",", ":"), default=str) != json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str):
                    raise CheckpointStoreBlocked(f"post-checkpoint INSERT stored row differs from payload: {replica_id}")
            else:  # DELETE
                try:
                    payload = json.loads(old_value)
                except (TypeError, ValueError) as exc:
                    raise CheckpointStoreBlocked(f"post-checkpoint DELETE payload is invalid: {replica_id}") from exc
                existing = read_row()
                if not isinstance(payload, dict) or existing is None or json.dumps(existing, sort_keys=True, separators=(",", ":"), default=str) != json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str):
                    raise CheckpointStoreBlocked(f"post-checkpoint DELETE precondition mismatch: {replica_id}")
                from backend.engine.fk_quarantine import ensure_quarantine_table, quarantine_orphans, verify_fk_integrity
                ensure_quarantine_table(expected)
                quarantine_orphans(expected, parent_table=table, parent_row_id=row_id)
                changed = expected.execute(f'DELETE FROM "{table_q}" WHERE "{pk_q}"=?', (row_id,))
                verify_fk_integrity(expected)
            if changed.rowcount != 1:
                raise CheckpointStoreBlocked(f"post-checkpoint operation did not replay exactly once: {replica_id}")
            try:
                violations = expected.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise CheckpointStoreBlocked(f"post-checkpoint replay violates foreign keys: {replica_id}")
            except sqlite3.DatabaseError as exc:
                raise CheckpointStoreBlocked(f"post-checkpoint replay is invalid: {replica_id}") from exc
            seen_operations.add(str(row[1] or row[0]))
        if _snapshot_data_fingerprint(expected) != live_data:
            raise CheckpointStoreBlocked(f"post-checkpoint data does not match tracked operation tail: {replica_id}")
        expected.commit()
    finally:
        expected.close()


def _reconcile_checkpoint_acknowledgements(manifest: dict[str, Any]) -> None:
    db_id = manifest.get("db_id")
    pending_by_replica: dict[str, list[dict[str, Any]]] = {}
    members = {item.get("replica_id"): item for item in manifest.get("replicas", [])}
    vectors = manifest.get("acknowledgements")
    if not isinstance(vectors, dict):
        raise CheckpointStoreBlocked("checkpoint acknowledgement vectors are invalid")
    if set(vectors) != set(members):
        raise CheckpointStoreBlocked("checkpoint ACK membership does not match checkpoint replicas")
    # Validate every member and every existing value before persisting any gap.
    for replica_id, vector in manifest.get("acknowledgements", {}).items():
        if not isinstance(vector, dict):
            raise CheckpointStoreBlocked(f"checkpoint ACK vector is invalid for {replica_id}")
        registered = app_state.get_replica(replica_id)
        member = members.get(replica_id)
        if not registered or not member or registered.get("db_path") != member.get("db_path") or registered.get("incarnation_id") != member.get("incarnation_id"):
            raise CheckpointStoreBlocked(f"registry membership disagrees with checkpoint for {replica_id}")
        current_vector = app_state.replica_acks.get(db_id, {}).get(replica_id, {})
        try:
            durable_vector = app_state.durable_replica_ack_vector(db_id, replica_id)
        except Exception as exc:
            raise CheckpointStoreBlocked(f"durable registry ACK evidence is unavailable for {replica_id}: {exc}") from exc
        if current_vector != durable_vector:
            raise CheckpointStoreBlocked(f"in-memory ACK state differs from durable registry for {replica_id}")
        missing = []
        for operation_id, evidence in vector.items():
            if not isinstance(evidence, dict) or evidence.get("payload_hash") != manifest.get("operation_hashes", {}).get(operation_id):
                raise CheckpointStoreBlocked(f"checkpoint ACK evidence is invalid: {replica_id}/{operation_id}")
            current = current_vector.get(operation_id)
            if current and current != evidence:
                raise CheckpointStoreBlocked(f"registry ACK conflicts with committed checkpoint: {replica_id}/{operation_id}")
            if not current:
                missing.append({"operation_id": operation_id, **evidence})
        pending_by_replica[replica_id] = missing
    for replica_id, missing in pending_by_replica.items():
        if missing:
            try:
                app_state.record_replica_acknowledgements(db_id, replica_id, missing)
                durable = app_state.durable_replica_ack_vector(db_id, replica_id)
                expected = manifest["acknowledgements"][replica_id]
                if any(durable.get(operation_id) != evidence for operation_id, evidence in expected.items()):
                    raise RuntimeError("registry did not durably publish the complete ACK vector")
            except Exception as exc:
                raise CheckpointStoreBlocked(f"registry ACK reconciliation failed: {exc}") from exc


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.post("/sync/compact", status_code=200)
@serialized_mutation
def compact_sync_logs(body: dict[str, str]) -> dict[str, Any]:
    """Create/recover a durable checkpoint before pruning acknowledged logs."""
    status = _checkpoint_store_status()
    if status["status"] != "ready":
        return {"status": "blocked", "pruned": 0, "reason": status.get("reason", "checkpoint store unavailable")}
    try:
        # Persist any migrated replica incarnation IDs before freezing membership.
        app_state.save()
    except Exception as exc:
        return {"status": "blocked", "pruned": 0, "reason": f"registry durability check failed: {exc}"}
    db_id = body.get("db_id", "")
    db_info = app_state.get_db(db_id)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")
    blocked_checkpoints: list[dict[str, str]] = []
    try:
        recoverable = list_recoverable_checkpoints(_checkpoint_store_path())
        for checkpoint in recoverable:
            try:
                _resume_checkpoint(checkpoint)
            except Exception as exc:
                blocked = {"checkpoint_id": checkpoint.get("checkpoint_id", "unknown"),
                           "db_id": checkpoint.get("manifest", {}).get("db_id", ""),
                           "reason": str(exc)}
                blocked_checkpoints.append(blocked)
                if blocked["db_id"] == db_id:
                    return {"status": "blocked", "pruned": 0, "reason": blocked["reason"],
                            "checkpoint_id": blocked["checkpoint_id"],
                            "blocked_checkpoints": blocked_checkpoints}
    except Exception as exc:
        return {"status": "blocked", "pruned": 0, "reason": str(exc),
                "blocked_checkpoints": blocked_checkpoints}
    replicas = app_state.list_replicas_for_db(db_id)
    replica_ids = [r["replica_id"] for r in replicas]
    vectors = app_state.replica_ack_vectors(db_id, replica_ids)
    common_ids, horizon = compactable_operation_ids(vectors) if vectors else (set(), None)
    if not common_ids or horizon is None:
        return {"status": "retained", "pruned": 0, "stable_horizon": None,
                "reason": "missing acknowledgement from one or more enrolled replicas",
                "blocked_checkpoints": blocked_checkpoints}
    common_payload_hashes = {
        operation_id: next(iter(vectors.values()))[operation_id]["payload_hash"]
        for operation_id in common_ids
    }
    checkpoint_id = str(uuid.uuid4())
    snapshots = []
    try:
        for replica in replicas:
            _verify_replica_history(replica["db_path"], common_payload_hashes)
        members = [{"replica_id": r["replica_id"], "db_path": r["db_path"], "incarnation_id": r.get("incarnation_id"), "parent_checkpoint_id": _replica_checkpoint_id(r["db_path"])} for r in replicas]
        membership = sorted((item["replica_id"], item.get("incarnation_id"), item["db_path"]) for item in members)
        membership_epoch = hashlib.sha256(json.dumps(membership, separators=(",", ":")).encode("utf-8")).hexdigest()
        snapshot_dir = DATA_DIR / "checkpoint_snapshots"
        for replica in replicas:
            snapshot_path = snapshot_dir / f"{checkpoint_id}_{replica['replica_id']}.sqlite"
            create_database_snapshot(replica["db_path"], snapshot_path)
            with sqlite3.connect(str(snapshot_path)) as snap:
                schema_fingerprint = _snapshot_schema_fingerprint(snap)
                operation_frontier = _snapshot_operation_frontier(snap)
                data_fingerprint = _snapshot_data_fingerprint(snap)
            snapshots.append({"checkpoint_id": checkpoint_id,
                              "replica_id": replica["replica_id"], "incarnation_id": replica.get("incarnation_id"),
                              "replica_db_path": replica["db_path"], "path": str(snapshot_path), "sha256": "",
                              "schema_fingerprint": schema_fingerprint,
                              "membership_epoch": membership_epoch, "operation_frontier": operation_frontier,
                              "data_fingerprint": data_fingerprint})
            with sqlite3.connect(str(snapshot_path)) as snap:
                snap.execute("CREATE TABLE _ss_checkpoint_snapshot_identity "
                             "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity_json TEXT NOT NULL)")
                identity_json = json.dumps(_snapshot_identity(snapshots[-1]), sort_keys=True,
                                           separators=(",", ":"), default=str)
                snap.execute("INSERT INTO _ss_checkpoint_snapshot_identity VALUES(1,?)", (identity_json,))
                snap.commit()
            snapshots[-1]["sha256"] = _sha256_file(snapshot_path)
        archived: dict[str, dict[str, Any]] = {}
        for replica in replicas:
            with connect_with_foreign_keys(replica["db_path"]) as conn:
                for row in conn.execute("SELECT id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,applied_at,op_type,origin_id,sequence,source_id,source_sequence,depends_on,bounded_delta,bounds_min,bounds_max FROM _ss_change_log"):
                    oid = str(row[11] or row[0])
                    if oid not in common_ids:
                        continue
                    phash = operation_payload_hash(row[4], row[5], row[1], row[2], row[3], row[10], row[13], row[14], row[15], row[16], row[17], row[18])
                    if phash != common_payload_hashes.get(oid):
                        raise CheckpointStoreBlocked(f"operation payload differs from ACK evidence: {oid}")
                    archived.setdefault(oid, {"operation_id": oid, "table_name": row[1], "row_id": row[2], "column_name": row[3], "old_value": row[4], "new_value": row[5], "op_type": row[10], "source_id": row[13], "source_sequence": row[14], "sequence": row[12], "replica_id": row[8], "ts_pt": row[6], "ts_l": row[7], "depends_on": row[15], "payload_hash": phash, "bounded_delta": row[16], "bounds_min": row[17], "bounds_max": row[18]})
        retained_archive = {}
        with sqlite3.connect(_checkpoint_store_path()) as conn:
            for operation_id, payload_json in conn.execute("SELECT operation_id,payload_json FROM archived_operations"):
                retained_archive[operation_id] = json.loads(payload_json).get("payload_hash")
        for operation_id, expected_hash in common_payload_hashes.items():
            if operation_id not in archived and retained_archive.get(operation_id) != expected_hash:
                raise CheckpointStoreBlocked(f"full operation payload unavailable for checkpoint: {operation_id}")
        manifest = {"checkpoint_id": checkpoint_id, "store_id": app_state.checkpoint_store_id, "db_id": db_id, "membership_epoch": membership_epoch, "replicas": members, "snapshots": snapshots, "operation_hashes": common_payload_hashes, "stable_horizon": horizon, "acknowledgements": vectors}
        write_checkpoint_record(_checkpoint_store_path(), checkpoint_id, manifest, list(archived.values()))
        result = _resume_checkpoint({"checkpoint_id": checkpoint_id, "manifest": manifest})
        return {"status": "completed", "stable_horizon": horizon,
                "enrolled_replicas": replica_ids, **result,
                "blocked_checkpoints": blocked_checkpoints}
    except Exception as exc:
        return {"status": "blocked", "checkpoint_id": checkpoint_id, "pruned": 0,
                "reason": str(exc), "blocked_checkpoints": blocked_checkpoints}


@router.post("/sync/generate-conflict", status_code=200)
@serialized_mutation
def generate_conflict(body: ConflictGenerateRequest) -> dict[str, Any]:
    """
    Simulation utility: writes divergent values to Replica A and Replica B to test conflict resolution.
    """
    rep_a_path = app_state.get_replica_path(body.replica_a_id)
    rep_b_path = app_state.get_replica_path(body.replica_b_id)

    if not rep_a_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_a_id}' not found.")
    if not rep_b_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_b_id}' not found.")

    assigned_policy = app_state.get_policy(body.db_id, body.table, body.column)
    bounded_bounds = None
    if assigned_policy and policy_base_name(assigned_policy) == "BOUNDED_SUM":
        try:
            bounded_bounds = parse_bounded_sum_bounds(assigned_policy)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    change_a = _sync_engine.apply_change(
        replica_db_path=rep_a_path,
        replica_id=body.replica_a_id,
        table=body.table,
        row_id=body.row_id,
        column=body.column,
        new_value=body.value_a,
        bounded_bounds=bounded_bounds,
    )

    change_b = _sync_engine.apply_change(
        replica_db_path=rep_b_path,
        replica_id=body.replica_b_id,
        table=body.table,
        row_id=body.row_id,
        column=body.column,
        new_value=body.value_b,
        bounded_bounds=bounded_bounds,
    )

    return {
        "status": "divergence_injected",
        "table": body.table,
        "row_id": body.row_id,
        "column": body.column,
        "replica_a_change_id": change_a,
        "replica_b_change_id": change_b,
    }


@router.post("/sync/increment", status_code=200)
@serialized_mutation
def apply_increment(body: IncrementRequest) -> dict[str, Any]:
    """Record an explicit additive operation on one registered replica."""
    replica = app_state.get_replica(body.replica_id)
    if not replica or replica.get("parent_db_id") != body.db_id:
        raise HTTPException(status_code=404, detail="Replica is not registered for this database.")
    path = app_state.get_replica_path(body.replica_id)
    if not path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_id}' not found.")
    try:
        operation_id = _sync_engine.apply_increment(
            path, body.replica_id, body.table, body.row_id, body.column, body.delta,
        )
    except (ValueError, OverflowError, RuntimeError, sqlite3.Error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with connect_with_foreign_keys(path) as conn:
        value = conn.execute(
            f'SELECT "{body.column.replace(chr(34), chr(34) * 2)}" '
            f'FROM "{body.table.replace(chr(34), chr(34) * 2)}" '
            f'WHERE "{_sync_engine._get_pk_column(conn, body.table)}"=?',
            (body.row_id,),
        ).fetchone()
    return {"status": "applied", "operation_id": operation_id,
            "replica_id": body.replica_id, "value": value[0] if value else None}
