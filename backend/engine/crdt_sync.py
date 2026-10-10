"""
crdt_sync.py
------------
Hybrid Logical Clock (HLC) implementation and the top-level replica
synchronisation engine for SemanticSync.

The ``CRDTSyncEngine`` orchestrates:
1. Replica creation (copying the base DB and initialising the change log).
2. Tracked writes to replicas (recording old/new values in ``_ss_change_log``).
3. Full three-way sync: detect → validate → resolve → write-back.

All SQL operations use parameterised queries.  No domain logic lives here.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .conflict_detector import ConflictDetector
from .merge_manager import MergeManager
from .policy_registry import PolicyRegistry, PolicyType
from .policy_validator import PolicyValidator
from .semantic_resolver import ResolutionResult, SemanticResolver


# ---------------------------------------------------------------------------
# Hybrid Logical Clock
# ---------------------------------------------------------------------------

@dataclass
class HLC:
    """
    Hybrid Logical Clock as described by Kulkarni et al. (2014).

    Combines a physical timestamp (wall-clock seconds) with a logical counter
    so that causally related events are always ordered, even when clocks are
    perfectly synchronised across nodes.

    Attributes
    ----------
    pt:
        Physical time in seconds (float).
    l:
        Logical counter (int, incremented on ties).
    node_id:
        Unique string identifier for this node.
    """
    pt: float = field(default_factory=time.time)
    l: int = 0
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # -----------------------------------------------------------------------
    # Clock advance
    # -----------------------------------------------------------------------

    def tick(
        self,
        recv_pt: float | None = None,
        recv_l: int | None = None,
    ) -> "HLC":
        """
        Advance the clock per the HLC send/receive algorithm.

        Call with no arguments on *send*; call with the remote clock values
        on *receive*.

        Returns
        -------
        HLC
            ``self`` (mutated in place and returned for chaining).
        """
        wall = time.time()

        if recv_pt is None:
            # Send event
            if wall > self.pt:
                self.pt = wall
                self.l = 0
            else:
                self.l += 1
        else:
            # Receive event
            max_pt = max(self.pt, recv_pt, wall)
            if max_pt == self.pt and max_pt == recv_pt:
                self.l = max(self.l, recv_l or 0) + 1
            elif max_pt == self.pt:
                self.l += 1
            elif max_pt == recv_pt:
                self.l = (recv_l or 0) + 1
            else:
                self.l = 0
            self.pt = max_pt

        return self

    # -----------------------------------------------------------------------
    # Comparison helpers
    # -----------------------------------------------------------------------

    def to_float(self) -> float:
        """Convert to a monotonically comparable float: ``pt * 1e6 + l``."""
        return self.pt * 1_000_000.0 + self.l

    def _tuple(self) -> tuple[float, int, str]:
        return (self.pt, self.l, self.node_id)

    def __lt__(self, other: "HLC") -> bool:  # type: ignore[override]
        return self._tuple() < other._tuple()

    def __le__(self, other: "HLC") -> bool:  # type: ignore[override]
        return self._tuple() <= other._tuple()

    def __gt__(self, other: "HLC") -> bool:  # type: ignore[override]
        return self._tuple() > other._tuple()

    def __ge__(self, other: "HLC") -> bool:  # type: ignore[override]
        return self._tuple() >= other._tuple()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HLC):
            return NotImplemented
        return self._tuple() == other._tuple()

    def __hash__(self) -> int:
        return hash(self._tuple())


# ---------------------------------------------------------------------------
# SyncResult
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    """Summary of a completed sync operation."""
    total_conflicts: int
    auto_resolved: int
    flagged_for_review: int
    applied_changes: list[dict[str, Any]]
    flagged_conflicts: list[str]   # conflict_ids
    duration_ms: float


# ---------------------------------------------------------------------------
# Change-log DDL
# ---------------------------------------------------------------------------

_CHANGE_LOG_DDL = """
CREATE TABLE IF NOT EXISTS _ss_change_log (
    id           TEXT PRIMARY KEY,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    column_name  TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    ts_pt        REAL NOT NULL,
    ts_l         INTEGER NOT NULL DEFAULT 0,
    replica_id   TEXT NOT NULL,
    applied_at   TEXT NOT NULL
)
"""


# ---------------------------------------------------------------------------
# CRDTSyncEngine
# ---------------------------------------------------------------------------

class CRDTSyncEngine:
    """
    Manages replica lifecycle and drives the full sync pipeline.

    Parameters
    ----------
    base_db_path:
        Path to the authoritative base SQLite database.
    data_dir:
        Directory where replica ``.db`` files are stored.
        Defaults to ``'data'`` (relative to the project root).
    """

    def __init__(self, base_db_path: str = "", data_dir: str = "data") -> None:
        self.base_db_path = base_db_path
        self.data_dir = data_dir
        self._clocks: dict[str, HLC] = {}          # replica_id -> HLC
        self._registry = PolicyRegistry()
        self._validator = PolicyValidator()
        self._resolver = SemanticResolver()
        self._manager = MergeManager()
        self._detector = ConflictDetector()

    # -----------------------------------------------------------------------
    # Replica management
    # -----------------------------------------------------------------------

    def create_replica(self, replica_id: str) -> str:
        """
        Fork the base database into a new replica.

        Parameters
        ----------
        replica_id:
            Logical name for the new replica (e.g. ``'node_alice'``).

        Returns
        -------
        str
            Absolute path to the new replica ``.db`` file.
        """
        import os
        os.makedirs(self.data_dir, exist_ok=True)
        dest = os.path.join(self.data_dir, f"{replica_id}.db")
        shutil.copy2(self.base_db_path, dest)

        # Initialise change log and HLC
        with sqlite3.connect(dest) as conn:
            conn.execute(_CHANGE_LOG_DDL)
            conn.commit()

        self._clocks[replica_id] = HLC(node_id=replica_id)
        return dest

    # -----------------------------------------------------------------------
    # Tracked writes
    # -----------------------------------------------------------------------

    def apply_change(
        self,
        replica_db_path: str,
        replica_id: str,
        table: str,
        row_id: Any,
        column: str,
        new_value: Any,
    ) -> str:
        """
        Write a new value to a replica and record the change in ``_ss_change_log``.

        Parameters
        ----------
        replica_db_path:
            Path to the replica ``.db`` file.
        replica_id:
            Logical identifier for this replica.
        table:
            Target table name.
        row_id:
            Primary key value of the target row.
        column:
            Target column name.
        new_value:
            The value to write.

        Returns
        -------
        str
            A UUID change_id for the log entry.

        Raises
        ------
        RuntimeError
            If the target row does not exist in the replica.
        """
        hlc = self._clocks.setdefault(replica_id, HLC(node_id=replica_id))
        hlc.tick()

        change_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(replica_db_path) as conn:
            conn.execute(_CHANGE_LOG_DDL)  # idempotent

            # Discover PK column name dynamically
            pk_col = self._get_pk_column(conn, table)
            if pk_col is None:
                raise RuntimeError(
                    f"Cannot apply change: table '{table}' has no single-column primary key."
                )

            # Read current (old) value with parameterised SQL
            row = conn.execute(
                f'SELECT "{column}" FROM "{table}" WHERE "{pk_col}" = ?',
                (row_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    f"Row with {pk_col}={row_id!r} not found in table '{table}'."
                )
            old_value = row[0]

            # Write new value
            conn.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "{pk_col}" = ?',
                (new_value, row_id),
            )

            # Log the change
            conn.execute(
                """
                INSERT INTO _ss_change_log
                    (id, table_name, row_id, column_name, old_value, new_value,
                     ts_pt, ts_l, replica_id, applied_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    table,
                    str(row_id),
                    column,
                    str(old_value) if old_value is not None else None,
                    str(new_value) if new_value is not None else None,
                    hlc.pt,
                    hlc.l,
                    replica_id,
                    now_iso,
                ),
            )
            conn.commit()

        return change_id

    # -----------------------------------------------------------------------
    # Change log query
    # -----------------------------------------------------------------------

    def get_changes_since(
        self,
        replica_db_path: str,
        since_ts: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Return all change log entries whose HLC ``to_float()`` exceeds *since_ts*.

        Parameters
        ----------
        replica_db_path:
            Path to the replica ``.db`` file.
        since_ts:
            Lower-bound timestamp (exclusive).  Default ``0.0`` returns all.

        Returns
        -------
        list[dict]
        """
        with sqlite3.connect(replica_db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM _ss_change_log
                    WHERE (ts_pt * 1000000.0 + ts_l) > ?
                    ORDER BY ts_pt ASC, ts_l ASC
                    """,
                    (since_ts,),
                ).fetchall()
            except sqlite3.OperationalError:
                return []

        return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Full sync pipeline
    # -----------------------------------------------------------------------

    def sync_replicas(
        self,
        replica_a_path: str,
        replica_b_path: str,
        base_path: str,
        replica_a_id: str,
        replica_b_id: str,
        policies: dict[str, dict[str, str]],
    ) -> SyncResult:
        """
        Run the full synchronisation pipeline between two replicas.

        Steps:
        1. Detect conflicts via ``ConflictDetector``.
        2. For each conflict: validate policy, resolve via ``SemanticResolver``.
        3. Write resolved values back to both replicas.
        4. REJECT conflicts are stored in ``MergeManager`` without write-back.

        Parameters
        ----------
        replica_a_path / replica_b_path:
            Paths to the two replica ``.db`` files.
        base_path:
            Path to the common base ``.db`` file.
        replica_a_id / replica_b_id:
            Logical identifiers for each replica.
        policies:
            Nested dict: ``{table: {column: policy_name}}``.
            Example: ``{"products": {"quantity": "SUM", "name": "LWW"}}``.

        Returns
        -------
        SyncResult
        """
        t_start = time.perf_counter()

        # 1 — detect
        conflicts = self._detector.detect(
            replica_a_db=replica_a_path,
            replica_b_db=replica_b_path,
            base_db=base_path,
            replica_a_id=replica_a_id,
            replica_b_id=replica_b_id,
        )

        applied_changes: list[dict[str, Any]] = []
        flagged_conflicts: list[str] = []
        auto_resolved = 0

        # 2 — resolve each conflict
        for conflict in conflicts:
            policy_name = (
                policies.get(conflict.table, {}).get(conflict.column, "REJECT")
            )

            # Validate policy vs column type (need normalised type)
            norm_type = self._get_column_norm_type(
                replica_a_path, conflict.table, conflict.column
            )
            validation = self._validator.validate(
                table=conflict.table,
                column=conflict.column,
                policy_name=policy_name,
                normalized_type=norm_type,
            )

            if not validation.valid:
                # Treat validation failures as REJECT
                policy = PolicyType.REJECT
            else:
                policy = validation.policy  # type: ignore[assignment]

            resolution: ResolutionResult = self._resolver.resolve(
                policy=policy,
                base_value=conflict.base_value,
                replica_a_value=conflict.replica_a_value,
                replica_b_value=conflict.replica_b_value,
                replica_a_ts=conflict.replica_a_ts,
                replica_b_ts=conflict.replica_b_ts,
                replica_a_id=replica_a_id,
                replica_b_id=replica_b_id,
            )

            if resolution.status == "flagged":
                # Store without write-back
                self._manager.add_conflict(conflict)
                self._manager.apply_resolution(conflict.conflict_id, resolution)
                flagged_conflicts.append(conflict.conflict_id)
            else:
                # 3 — write-back to both replicas
                resolved_val = resolution.resolved_value
                self._write_resolved(
                    replica_a_path, replica_a_id,
                    conflict.table, conflict.row_id, conflict.column, resolved_val,
                )
                self._write_resolved(
                    replica_b_path, replica_b_id,
                    conflict.table, conflict.row_id, conflict.column, resolved_val,
                )
                auto_resolved += 1
                applied_changes.append(
                    {
                        "conflict_id": conflict.conflict_id,
                        "table": conflict.table,
                        "row_id": conflict.row_id,
                        "column": conflict.column,
                        "resolved_value": resolved_val,
                        "policy": policy.value,
                        "explanation": resolution.explanation,
                    }
                )

        duration_ms = (time.perf_counter() - t_start) * 1000.0

        return SyncResult(
            total_conflicts=len(conflicts),
            auto_resolved=auto_resolved,
            flagged_for_review=len(flagged_conflicts),
            applied_changes=applied_changes,
            flagged_conflicts=flagged_conflicts,
            duration_ms=duration_ms,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_pk_column(conn: sqlite3.Connection, table: str) -> str | None:
        pragma = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        pks = [row[1] for row in pragma if row[5] == 1]   # column index 5 = pk flag
        return pks[0] if len(pks) == 1 else None

    def _get_column_norm_type(
        self, db_path: str, table: str, column: str
    ) -> str:
        """Read the normalised type for a column from a live database."""
        from .schema_inspector import SchemaInspector
        inspector = SchemaInspector(db_path)
        cols = inspector.inspect_table(table)
        for col in cols:
            col_name = col.get("name") if isinstance(col, dict) else getattr(col, "name", None)
            norm_type = col.get("normalized_type") if isinstance(col, dict) else getattr(col, "normalized_type", "TEXT")
            if col_name == column:
                return norm_type
        return "TEXT"  # safe fallback

    def _write_resolved(
        self,
        db_path: str,
        replica_id: str,
        table: str,
        row_id: Any,
        column: str,
        value: Any,
    ) -> None:
        """Write a resolved value back to a replica, logging to change log."""
        try:
            self.apply_change(db_path, replica_id, table, row_id, column, value)
        except RuntimeError:
            # Row may not exist on one replica (insert-delete race) — skip
            pass
