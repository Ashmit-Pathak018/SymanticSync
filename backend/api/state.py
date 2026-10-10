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
import threading
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

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────

    def load(self) -> None:
        """Load state from disk.  Safe to call multiple times (idempotent)."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if REGISTRY_FILE.exists():
            try:
                raw = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
                with self._lock:
                    self.databases = raw.get("databases", {})
                    self.replicas = raw.get("replicas", {})
                    self.policies = raw.get("policies", {})
                    self.conflicts = raw.get("conflicts", {})
                    self.metrics = raw.get("metrics", {})
            except (json.JSONDecodeError, OSError):
                # Corrupt file — reset to empty state but keep the file for inspection
                with self._lock:
                    self.databases = {}
                    self.replicas = {}
                    self.policies = {}
                    self.conflicts = {}
                    self.metrics = {}
        else:
            # First run — write an empty registry
            self.save()

    def save(self) -> None:
        """Persist current state to disk."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "databases": self.databases,
            "replicas": self.replicas,
            "policies": self.policies,
            "conflicts": self.conflicts,
            "metrics": self.metrics,
        }
        REGISTRY_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

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
        if "created_at" not in rec:
            import time
            rec["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self.replicas[replica_id] = rec
            self.save()

    def list_replicas_for_db(self, db_id: str) -> list[dict]:
        """Return all replicas that belong to *db_id*."""
        return [r for r in self.replicas.values() if r.get("parent_db_id") == db_id]

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
