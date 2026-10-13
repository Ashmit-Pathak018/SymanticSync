"""Durable, fail-closed coordinator for local checkpoint operations.

The coordinator is deliberately single-process. Its SQLite journal is the
source of truth for committed checkpoint manifests and archived operations;
the JSON application registry is only a catalog/ACK input.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from .mutation_lock import MUTATION_CHECKPOINT_LOCK, serialized_mutation


class CheckpointStoreError(RuntimeError):
    pass


class CheckpointStoreBlocked(CheckpointStoreError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("""CREATE TABLE checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK(state IN ('PREPARING','COMMITTED','PRUNING','COMPLETE','BLOCKED')),
        manifest_json TEXT NOT NULL, manifest_hash TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE archived_operations (
        checkpoint_id TEXT NOT NULL, operation_id TEXT NOT NULL,
        payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
        PRIMARY KEY(checkpoint_id, operation_id),
        FOREIGN KEY(checkpoint_id) REFERENCES checkpoints(checkpoint_id)
    )""")


def initialize_checkpoint_store(path: str | Path) -> str:
    """Explicitly initialize a new store; never called implicitly on open."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise CheckpointStoreBlocked("checkpoint store already exists; refusing reinitialization")
    with MUTATION_CHECKPOINT_LOCK:
        staging = target.with_name(target.name + ".initializing")
        if staging.exists():
            staged = validate_checkpoint_store(staging)
            if staged["checkpoints"]:
                raise CheckpointStoreBlocked("staged checkpoint store contains history; manual recovery required")
            os.replace(staging, target)
            return str(staged["store_id"])
        conn = _connect(staging)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("BEGIN IMMEDIATE")
            _schema(conn)
            store_id = str(uuid.uuid4())
            conn.execute("INSERT INTO store_meta VALUES('store_id', ?)", (store_id,))
            conn.execute("INSERT INTO store_meta VALUES('schema_version', '1')")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        with staging.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(staging, target)
        return store_id


def validate_checkpoint_store(path: str | Path, *, expected_store_id: str | None = None) -> dict[str, Any]:
    """Open and validate existing state without creating or repairing it."""
    target = Path(path)
    if not target.exists():
        raise CheckpointStoreBlocked("checkpoint store is missing; pruning is blocked")
    try:
        conn = _connect(target)
        try:
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise CheckpointStoreBlocked(f"checkpoint store quick_check failed: {check}")
            required = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"store_meta", "checkpoints", "archived_operations"} <= required:
                raise CheckpointStoreBlocked("checkpoint store schema is incomplete")
            expected_columns = {
                "store_meta": {"key", "value"},
                "checkpoints": {"checkpoint_id", "state", "manifest_json", "manifest_hash", "created_at"},
                "archived_operations": {"checkpoint_id", "operation_id", "payload_json", "payload_hash"},
            }
            for table, columns in expected_columns.items():
                actual_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if not columns <= actual_columns:
                    raise CheckpointStoreBlocked(f"checkpoint store schema is invalid: {table}")
            if str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "delete":
                raise CheckpointStoreBlocked("checkpoint store journal mode is not durable rollback mode")
            meta = dict(conn.execute("SELECT key,value FROM store_meta"))
            if meta.get("schema_version") != "1" or not meta.get("store_id"):
                raise CheckpointStoreBlocked("checkpoint store identity/version is invalid")
            if expected_store_id and expected_store_id != meta["store_id"]:
                raise CheckpointStoreBlocked("checkpoint store identity differs from registry marker")
            manifest_store_ids: set[str] = set()
            for row in conn.execute("SELECT checkpoint_id,state,manifest_json,manifest_hash FROM checkpoints"):
                actual = hashlib.sha256(row["manifest_json"].encode("utf-8")).hexdigest()
                if actual != row["manifest_hash"]:
                    raise CheckpointStoreBlocked(f"checkpoint manifest hash mismatch: {row['checkpoint_id']}")
                manifest = json.loads(row["manifest_json"])
                if row["checkpoint_id"] != manifest.get("checkpoint_id"):
                    raise CheckpointStoreBlocked("checkpoint identity differs from its manifest")
                if row["state"] not in {"COMMITTED", "PRUNING", "COMPLETE"}:
                    continue
                if manifest.get("store_id") != meta["store_id"]:
                    raise CheckpointStoreBlocked("checkpoint manifest has no matching durable store identity")
                manifest_store_ids.add(str(manifest["store_id"]))
                for snapshot in manifest.get("snapshots", []):
                    snapshot_path = Path(snapshot["path"])
                    if not snapshot_path.exists() or file_sha256(snapshot_path) != snapshot["sha256"]:
                        raise CheckpointStoreBlocked(f"checkpoint snapshot missing or corrupt: {snapshot.get('replica_id')}")
                    with sqlite3.connect(str(snapshot_path)) as snap:
                        if snap.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                            raise CheckpointStoreBlocked(f"checkpoint snapshot failed integrity check: {snapshot.get('replica_id')}")
            for row in conn.execute("SELECT payload_json,payload_hash FROM archived_operations"):
                actual = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if actual != row["payload_hash"]:
                    raise CheckpointStoreBlocked("archived operation payload hash mismatch")
            archived_payloads: dict[str, str] = {}
            for row in conn.execute("SELECT operation_id,payload_json FROM archived_operations"):
                payload = json.loads(row["payload_json"])
                payload_hash = str(payload.get("payload_hash", ""))
                if row["operation_id"] in archived_payloads and archived_payloads[row["operation_id"]] != payload_hash:
                    raise CheckpointStoreBlocked(f"operation archive identity collision: {row['operation_id']}")
                archived_payloads[row["operation_id"]] = payload_hash
            for row in conn.execute("SELECT state,manifest_json FROM checkpoints WHERE state IN ('COMMITTED','PRUNING','COMPLETE')"):
                manifest = json.loads(row["manifest_json"])
                for operation_id, expected_hash in manifest.get("operation_hashes", {}).items():
                    if archived_payloads.get(operation_id) != expected_hash:
                        raise CheckpointStoreBlocked(f"checkpoint operation archive is missing or mismatched: {operation_id}")
            manifests = [json.loads(row[0]) for row in conn.execute(
                "SELECT manifest_json FROM checkpoints WHERE state IN ('COMMITTED','PRUNING','COMPLETE')")]
            return {"status": "ready", "store_id": meta["store_id"],
                    "checkpoints": conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0],
                    "manifest_store_ids": sorted(manifest_store_ids), "manifests": manifests}
        finally:
            conn.close()
    except CheckpointStoreBlocked:
        raise
    except (OSError, sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
        raise CheckpointStoreBlocked(f"checkpoint store cannot be validated: {exc}") from exc


def write_checkpoint_record(path: str | Path, checkpoint_id: str, manifest: dict[str, Any],
                            operations: list[dict[str, Any]]) -> None:
    """Durably commit an immutable manifest and payload archive, idempotently."""
    target = Path(path)
    validate_checkpoint_store(target)
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    with MUTATION_CHECKPOINT_LOCK:
        conn = _connect(target)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT state,manifest_hash FROM checkpoints WHERE checkpoint_id=?",
                                    (checkpoint_id,)).fetchone()
            if existing:
                if existing["manifest_hash"] != manifest_hash:
                    raise CheckpointStoreBlocked("checkpoint ID reused with different manifest")
            else:
                conn.execute("INSERT INTO checkpoints VALUES(?,?,?,?,datetime('now'))",
                             (checkpoint_id, "PREPARING", manifest_json, manifest_hash))
            conn.commit()

            # Archive and commit are separate durable steps. A crash here leaves
            # PREPARING, which is safe to resume and never authorizes pruning.
            conn.execute("BEGIN IMMEDIATE")
            for operation in operations:
                payload_json = json.dumps(operation, sort_keys=True, separators=(",", ":"), default=str)
                payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                row = conn.execute("SELECT payload_hash FROM archived_operations WHERE checkpoint_id=? AND operation_id=?",
                                   (checkpoint_id, str(operation["operation_id"]))).fetchone()
                if row and row["payload_hash"] != payload_hash:
                    raise CheckpointStoreBlocked("operation archive identity collision")
                conn.execute("INSERT OR IGNORE INTO archived_operations VALUES(?,?,?,?)",
                             (checkpoint_id, str(operation["operation_id"]), payload_json, payload_hash))
            if not existing or existing["state"] == "PREPARING":
                conn.execute("UPDATE checkpoints SET state='COMMITTED' WHERE checkpoint_id=?", (checkpoint_id,))
            elif existing["state"] == "BLOCKED":
                raise CheckpointStoreBlocked("blocked checkpoint cannot be recommitted")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def set_checkpoint_state(path: str | Path, checkpoint_id: str, state: str) -> None:
    validate_checkpoint_store(path)
    with MUTATION_CHECKPOINT_LOCK, closing(_connect(Path(path))) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT state FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone()
            if not row:
                raise CheckpointStoreBlocked("checkpoint journal entry is missing")
            allowed = {"PREPARING": {"COMMITTED", "BLOCKED"},
                       "COMMITTED": {"PRUNING", "COMPLETE", "BLOCKED"},
                       "PRUNING": {"PRUNING", "COMPLETE", "BLOCKED"},
                       "COMPLETE": {"COMPLETE"}, "BLOCKED": {"BLOCKED"}}
            if state not in allowed[row["state"]]:
                raise CheckpointStoreBlocked(f"invalid checkpoint transition {row['state']} -> {state}")
            conn.execute("UPDATE checkpoints SET state=? WHERE checkpoint_id=?", (state, checkpoint_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_recoverable_checkpoints(path: str | Path) -> list[dict[str, Any]]:
    validate_checkpoint_store(path)
    with closing(_connect(Path(path))) as conn:
        rows = conn.execute("SELECT checkpoint_id,state,manifest_json FROM checkpoints "
                            "WHERE state IN ('COMMITTED','PRUNING') ORDER BY created_at").fetchall()
        return [{"checkpoint_id": row[0], "state": row[1], "manifest": json.loads(row[2])} for row in rows]


def checkpoint_state(path: str | Path, checkpoint_id: str) -> str:
    validate_checkpoint_store(path)
    with closing(_connect(Path(path))) as conn:
        row = conn.execute("SELECT state FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone()
        if not row:
            raise CheckpointStoreBlocked("checkpoint journal entry is missing")
        return str(row[0])


def latest_completed_checkpoint(path: str | Path, db_id: str) -> dict[str, Any] | None:
    validate_checkpoint_store(path)
    with closing(_connect(Path(path))) as conn:
        rows = conn.execute("SELECT checkpoint_id,manifest_json FROM checkpoints WHERE state='COMPLETE' ORDER BY rowid DESC").fetchall()
        for row in rows:
            manifest = json.loads(row["manifest_json"])
            if manifest.get("db_id") == db_id:
                return {"checkpoint_id": row["checkpoint_id"], "manifest": manifest}
    return None


@serialized_mutation
def create_database_snapshot(source: str | Path, destination: str | Path) -> str:
    """Create a consistent SQLite backup and return its content digest."""
    source_path, target_path = Path(source), Path(destination)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        return file_sha256(target_path)
    temporary = target_path.with_name(target_path.name + ".preparing")
    if temporary.exists():
        raise CheckpointStoreBlocked(f"unfinished snapshot staging file exists: {temporary.name}")
    src = sqlite3.connect(str(source_path), timeout=10)
    dst = sqlite3.connect(str(temporary), timeout=10)
    try:
        src.backup(dst)
        dst.commit()
    except Exception:
        dst.close()
        src.close()
        raise
    dst.close()
    src.close()
    with temporary.open("rb+") as stream:
        os.fsync(stream.fileno())
    digest = file_sha256(temporary)
    os.replace(temporary, target_path)
    return digest


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()