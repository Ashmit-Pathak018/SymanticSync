"""
backend/api/state.py
────────────────────
Global application state for SemanticSync.

Manages:
  • Registered databases  (db_id → DatabaseInfo dict)
  • Registered replicas   (replica_id → ReplicaInfo dict)
  • Policy assignments    ("db_id:table:column" → policy_name string)
  • Latest benchmark metrics (workload → BenchmarkMetrics dict)
  • In-flight conflicts   (conflict_id → conflict record dict)

All state is persisted as JSON at data/registry.json so it survives
server restarts without an external database.  Thread-safety for the
single-process dev server is provided by a threading.Lock.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR = Path(os.environ.get("SEMANTICSYNC_DATA_DIR", str(DEFAULT_DATA_DIR)))
REGISTRY_FILE = DATA_DIR / "registry.json"

# Shape of the serialised registry file:
# {
#   "databases": { <db_id>: {...DatabaseInfo fields...} },
#   "replicas":  { <replica_id>: {...ReplicaInfo fields...} },
#   "policies":  { "<db_id>:<table>:<column>": "<policy_name>" },
#   "conflicts": { <conflict_id>: {...conflict record...} },
#   "metrics":   { <workload>: {...BenchmarkMetrics fields...} }
# }

_EMPTY_REGISTRY: dict[str, Any] = {
    "databases": {},
    "replicas": {},
    "policies": {},
    "conflicts": {},
    "metrics": {},
    "replica_acks": {},
}


class AppState:
    """
    Thread-safe in-memory state store backed by a JSON registry file.

    All mutating methods call ``save()`` automatically so the on-disk
    state is always consistent with memory.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.databases: dict[str, dict] = {}   # db_id  → DatabaseInfo dict
        self.replicas: dict[str, dict] = {}    # replica_id → ReplicaInfo dict
        self.policies: dict[str, str] = {}     # "db_id:table:column" → policy_name
        self.conflicts: dict[str, dict] = {}   # conflict_id → conflict record dict
        self.metrics: dict[str, dict] = {}     # workload → BenchmarkMetrics dict
        self.replica_acks: dict[str, dict[str, dict[str, dict]]] = {}
        self.checkpoint_store_id: str | None = None
        self.registry_load_error: str | None = None

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────

    def load(self) -> None:
        """Load state from disk.  Safe to call multiple times (idempotent)."""
        self.registry_load_error = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if REGISTRY_FILE.exists():
            try:
                raw = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
                migrated_incarnations = False
                with self._lock:
                    self.databases = raw.get("databases", {})
                    self.replicas = raw.get("replicas", {})
                    for replica_id, replica in self.replicas.items():
                        if isinstance(replica, dict):
                            if not replica.get("incarnation_id"):
                                replica["incarnation_id"] = str(uuid.uuid4())
                                migrated_incarnations = True
                    self.policies = raw.get("policies", {})
                    self.conflicts = raw.get("conflicts", {})
                    self.metrics = raw.get("metrics", {})
                    self.replica_acks = raw.get("replica_acks", {})
                    self.checkpoint_store_id = raw.get("checkpoint_store_id")
                if migrated_incarnations:
                    try:
                        self.save()
                    except OSError:
                        # Keep the valid loaded registry in memory. Compaction
                        # explicitly retries this save before committing a manifest.
                        pass
            except (json.JSONDecodeError, OSError):
                # Corrupt file — reset to empty state but keep the file for inspection
                with self._lock:
                    self.databases = {}
                    self.replicas = {}
                    self.policies = {}
                    self.conflicts = {}
                    self.metrics = {}
                    self.replica_acks = {}
                    self.checkpoint_store_id = None
                    self.registry_load_error = "registry JSON is corrupt or unreadable"
        else:
            # Do not replace a missing registry when a checkpoint store may
            # contain the only durable membership/history record.
            if (DATA_DIR / "checkpoint_store.sqlite").exists():
                self.registry_load_error = "registry is missing while checkpoint history may exist"
            else:
                # First run — write an empty registry.
                self.save()

    def save(self) -> None:
        """Persist current state to disk."""
        if self.registry_load_error:
            raise RuntimeError("Registry is corrupt; refusing to overwrite it automatically.")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "databases": self.databases,
            "replicas": self.replicas,
            "policies": self.policies,
            "conflicts": self.conflicts,
            "metrics": self.metrics,
            "replica_acks": self.replica_acks,
            "checkpoint_store_id": self.checkpoint_store_id,
        }
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=DATA_DIR,
                prefix=f".{REGISTRY_FILE.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = temporary.name
                json.dump(payload, temporary, indent=2, default=str)
                temporary.flush()
                os.fsync(temporary.fileno())
            for attempt in range(10):
                try:
                    os.replace(temporary_path, REGISTRY_FILE)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.05)
        except Exception:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except Exception:
                    pass
            raise

    def set_checkpoint_store_id(self, store_id: str) -> None:
        """Persist the checkpoint-store identity used to detect loss/corruption."""
        with self._lock:
            if self.checkpoint_store_id not in (None, store_id):
                raise ValueError("A different checkpoint store is already registered.")
            self.checkpoint_store_id = store_id
            self.save()

    # ──────────────────────────────────────────────
    # Database helpers
    # ──────────────────────────────────────────────

    def get_db(self, db_id: str) -> dict | None:
        """Return the DatabaseInfo dict for *db_id*, or ``None`` if not registered."""
        return self.databases.get(db_id)

    def get_db_path(self, db_id: str) -> str | None:
        """Return the filesystem path for *db_id*, or ``None``."""
        info = self.databases.get(db_id)
        return info["path"] if info else None

    def register_db(self, db_id: str, info: dict | None = None, **kwargs) -> None:
        """Persist a new database entry."""
        rec = dict(info) if info else {}
        rec.update(kwargs)
        rec.setdefault("id", db_id)
        if "table_count" not in rec and "path" in rec:
            try:
                from backend.engine.schema_inspector import SchemaInspector
                rec["table_count"] = SchemaInspector(rec["path"]).table_count()
            except Exception:
                rec["table_count"] = 0
        if "created_at" not in rec:
            import time
            rec["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self.databases[db_id] = rec
            self.save()

    def list_databases(self) -> list[dict]:
        """Return all registered databases as a list."""
        return list(self.databases.values())

    # ──────────────────────────────────────────────
    # Replica helpers
    # ──────────────────────────────────────────────

    def get_replica_path(self, replica_id: str) -> str | None:
        """Return the filesystem path for *replica_id*, or ``None``."""
        info = self.replicas.get(replica_id)
        return info["db_path"] if info else None

    def get_replica(self, replica_id: str) -> dict | None:
        """Return the ReplicaInfo dict for *replica_id*, or ``None``."""
        return self.replicas.get(replica_id)

    def register_replica(self, replica_id: str, info: dict | None = None, **kwargs) -> None:
        """Persist a new replica entry."""
        rec = dict(info) if info else {}
        rec.update(kwargs)
        rec.setdefault("replica_id", replica_id)
        prior = self.replicas.get(replica_id)
        if prior and prior.get("db_path") == rec.get("db_path"):
            rec.setdefault("incarnation_id", prior.get("incarnation_id") or str(uuid.uuid4()))
        else:
            rec.setdefault("incarnation_id", str(uuid.uuid4()))
        if "created_at" not in rec:
            import time
            rec["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self.replicas[replica_id] = rec
            self.save()

    def list_replicas_for_db(self, db_id: str) -> list[dict]:
        """Return all replicas that belong to *db_id*."""
        return [r for r in self.replicas.values() if r.get("parent_db_id") == db_id]

    def record_replica_acknowledgements(
        self, db_id: str, replica_id: str, operations: list[dict],
    ) -> None:
        """Persist exact operation receipts as this replica's acknowledgement vector."""
        if not operations:
            return
        with self._lock:
            db_existed = db_id in self.replica_acks
            replica_existed = db_existed and replica_id in self.replica_acks[db_id]
            vector = self.replica_acks.setdefault(db_id, {}).setdefault(replica_id, {})
            previous = dict(vector)
            try:
                for operation in operations:
                    operation_id = str(operation["operation_id"])
                    vector[operation_id] = {
                        "source_id": str(operation["source_id"]),
                        "source_sequence": int(operation["source_sequence"]),
                        "ts_pt": float(operation["ts_pt"]),
                        "ts_l": int(operation["ts_l"]),
                        "payload_hash": operation.get("payload_hash"),
                    }
                self.save()
            except Exception:
                # save() publishes via atomic replace. Restore the in-memory
                # vector if publication fails so retries cannot mistake an
                # unpersisted acknowledgement for durable evidence.
                if replica_existed:
                    vector.clear()
                    vector.update(previous)
                else:
                    self.replica_acks[db_id].pop(replica_id, None)
                    if not db_existed:
                        self.replica_acks.pop(db_id, None)
                raise

    def durable_replica_ack_vector(self, db_id: str, replica_id: str) -> dict[str, dict]:
        """Read one ACK vector from the atomically published registry file."""
        if self.registry_load_error:
            raise RuntimeError("Registry is corrupt; durable ACK evidence is unavailable.")
        try:
            raw = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Registry cannot be read to verify durable ACK evidence.") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("replica_acks", {}), dict):
            raise RuntimeError("Registry ACK evidence has an invalid shape.")
        db_vectors = raw.get("replica_acks", {}).get(db_id, {})
        if not isinstance(db_vectors, dict):
            raise RuntimeError(f"Registry ACK evidence is invalid for database {db_id}.")
        vector = db_vectors.get(replica_id, {})
        if not isinstance(vector, dict):
            raise RuntimeError(f"Registry ACK evidence is invalid for replica {replica_id}.")
        return vector

    def replica_ack_vectors(self, db_id: str, replica_ids: list[str]) -> dict[str, dict]:
        """Return vectors only when they cover the exact enrolled replica set."""
        current_ids = {r["replica_id"] for r in self.list_replicas_for_db(db_id)}
        requested = set(replica_ids)
        stored = self.replica_acks.get(db_id, {})
        if not requested or requested != current_ids or any(rid not in stored for rid in requested):
            return {}
        return {rid: dict(stored[rid]) for rid in requested}

    # ──────────────────────────────────────────────
    # Policy helpers
    # ──────────────────────────────────────────────

    def _policy_key(self, db_id: str, table: str, column: str) -> str:
        return f"{db_id}:{table}:{column}"

    def set_policy(self, db_id: str, table: str, column: str, policy: str) -> None:
        """Assign *policy* to the given table/column within *db_id*."""
        with self._lock:
            self.policies[self._policy_key(db_id, table, column)] = policy
            self.save()

    def get_policy(self, db_id: str, table: str, column: str) -> str | None:
        """Return the active policy for *db_id:table:column*, or ``None``."""
        return self.policies.get(self._policy_key(db_id, table, column))

    def get_policies_for_db(self, db_id: str) -> dict[str, str]:
        """
        Return all policy assignments for *db_id* as a dict mapping
        ``"table:column"`` → policy_name.
        """
        prefix = f"{db_id}:"
        return {
            key[len(prefix):]: policy
            for key, policy in self.policies.items()
            if key.startswith(prefix)
        }

    def delete_policy(self, db_id: str, table: str, column: str) -> bool:
        """Remove a policy assignment. Returns True if the key existed."""
        key = self._policy_key(db_id, table, column)
        with self._lock:
            existed = key in self.policies
            if existed:
                del self.policies[key]
                self.save()
        return existed

    # ──────────────────────────────────────────────
    # Conflict helpers
    # ──────────────────────────────────────────────

    def store_conflict(self, conflict_id: str, record: dict) -> None:
        """Persist or overwrite a conflict record."""
        with self._lock:
            self.conflicts[conflict_id] = record
            self.save()

    def get_conflict(self, conflict_id: str) -> dict | None:
        """Return a single conflict record by ID, or ``None``."""
        return self.conflicts.get(conflict_id)

    def list_conflicts(
        self,
        status: str = "all",
        db_id: str | None = None,
    ) -> list[dict]:
        """
        Return conflicts filtered by *status* and optionally by *db_id*.

        Parameters
        ----------
        status:
            ``'all'`` | ``'pending'`` | ``'resolved'`` | ``'flagged'``
        db_id:
            If provided, only return conflicts belonging to this database.
        """
        results = list(self.conflicts.values())
        if db_id:
            results = [c for c in results if c.get("db_id") == db_id]
        if status != "all":
            results = [c for c in results if c.get("status") == status]
        return results

    def store_conflicts_batch(self, records: list[dict]) -> None:
        """Bulk-persist a list of conflict records (each must have a ``conflict_id``)."""
        with self._lock:
            for record in records:
                self.conflicts[record["conflict_id"]] = record
            self.save()

    # ──────────────────────────────────────────────
    # Metrics helpers
    # ──────────────────────────────────────────────

    def store_metrics(self, workload: str, metrics: dict) -> None:
        """Cache the latest benchmark result for *workload*."""
        with self._lock:
            self.metrics[workload] = metrics
            self.save()

    def set_metrics(self, workload: str, metrics: dict) -> None:
        """Alias for store_metrics."""
        self.store_metrics(workload, metrics)

    def get_metrics(self, workload: str | None = None) -> dict:
        """Return metrics for *workload*, or all metrics if *workload* is None."""
        if workload:
            return self.metrics.get(workload, {})
        return dict(self.metrics)


# Module-level singleton used by all route modules.
app_state = AppState()
