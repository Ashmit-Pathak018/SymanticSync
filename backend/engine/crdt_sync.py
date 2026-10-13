"""
crdt_sync.py
------------
Hybrid Logical Clock (HLC) implementation and the top-level replica
synchronisation engine for SemanticSync.

The ``CRDTSyncEngine`` orchestrates:
1. Replica creation (copying the base DB and initialising the change log).
2. Tracked writes to replicas (recording operations in ``_ss_change_log``).
3. Pairwise operation delivery followed by three-way detect → resolve → write-back.

All SQL operations use parameterised queries.  No domain logic lives here.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .conflict_detector import ConflictDetector
from .fk_quarantine import (
    connect_with_foreign_keys,
    ensure_quarantine_table,
    quarantine_orphans,
    verify_fk_integrity,
)
from .merge_manager import MergeManager
from .policy_registry import PolicyRegistry, PolicyType, parse_bounded_sum_bounds, policy_base_name
from .policy_validator import PolicyValidator
from .semantic_resolver import ResolutionResult, SemanticResolver
from .log_compaction import ensure_compaction_tables, operation_payload_hash
from .mutation_lock import serialized_mutation


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
    skipped_tables: list[str] = field(default_factory=list)
    """Tables skipped because they have no single-column primary key."""
    rejected_operations: list[dict[str, Any]] = field(default_factory=list)
    """Operations held for missing causal dependencies or divergent receiver state."""
    acknowledgements: list[dict[str, Any]] = field(default_factory=list)
    """Exact operation receipts verified by a receiving replica during this sync."""


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
    applied_at   TEXT NOT NULL,
    op_type      TEXT NOT NULL DEFAULT 'UPDATE',
    origin_id    TEXT,
    sequence     INTEGER,
    source_id    TEXT,
    source_sequence INTEGER,
    depends_on   TEXT NOT NULL DEFAULT '[]',
    bounded_delta NUMERIC,
    bounds_min NUMERIC,
    bounds_max NUMERIC
)
"""

def _ensure_change_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CHANGE_LOG_DDL)
    # Migrate legacy schemas only when a column is first introduced. This
    # function is called on every received operation, so unconditional
    # backfills turn a long replay into repeated full change-log scans.
    pragma = conn.execute('PRAGMA table_info("_ss_change_log")').fetchall()
    col_names = [r[1] for r in pragma]
    if "op_type" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN op_type TEXT NOT NULL DEFAULT 'UPDATE'")
    if "origin_id" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN origin_id TEXT")
    if "sequence" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN sequence INTEGER")
        conn.execute("UPDATE _ss_change_log SET sequence = rowid WHERE sequence IS NULL")
    if "source_id" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN source_id TEXT")
    if "source_sequence" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN source_sequence INTEGER")
    if "depends_on" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN depends_on TEXT NOT NULL DEFAULT '[]'")
    if "bounded_delta" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN bounded_delta NUMERIC")
    if "bounds_min" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN bounds_min NUMERIC")
    if "bounds_max" not in col_names:
        conn.execute("ALTER TABLE _ss_change_log ADD COLUMN bounds_max NUMERIC")
    if "origin_id" not in col_names:
        conn.execute("UPDATE _ss_change_log SET origin_id = id WHERE origin_id IS NULL OR origin_id = ''")
    if "source_id" not in col_names:
        conn.execute("UPDATE _ss_change_log SET source_id = replica_id WHERE source_id IS NULL OR source_id = ''")
    if "source_sequence" not in col_names:
        conn.execute("UPDATE _ss_change_log SET source_sequence = sequence WHERE source_sequence IS NULL")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS _ss_change_log_sequence_idx "
        "ON _ss_change_log(sequence)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS _ss_change_log_origin_idx "
        "ON _ss_change_log(origin_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS _ss_change_log_source_row_idx "
        "ON _ss_change_log(table_name, row_id, source_id, source_sequence)"
    )


def _next_change_sequence(conn: sqlite3.Connection) -> int:
    ensure_compaction_tables(conn)
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence),0)+1 FROM ("
        "SELECT sequence FROM _ss_change_log UNION ALL "
        "SELECT sequence FROM _ss_compacted_receipts)"
    ).fetchone()
    return int(row[0])


def _row_dependency_ids(conn: sqlite3.Connection, table: str, row_id: Any, schema: str = "main") -> list[str]:
    """Return the latest known operation identity for a row in one log stream."""
    ensure_compaction_tables(conn, schema)
    row = conn.execute(
        f"SELECT origin_id FROM (SELECT origin_id,sequence,table_name,row_id FROM {schema}._ss_change_log "
        f"UNION ALL SELECT origin_id,sequence,table_name,row_id FROM {schema}._ss_compacted_receipts) "
        "WHERE table_name=? AND row_id=? ORDER BY sequence DESC LIMIT 1",
        (table, str(row_id)),
    ).fetchone()
    return [str(row[0])] if row and row[0] else []


class _OperationSavepointConnection:
    """Give a replayed operation its own rollback boundary in a sync batch."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters: Any = ()):
        if sql == "BEGIN IMMEDIATE":
            return self._connection.execute("SAVEPOINT _ss_received_operation", parameters)
        return self._connection.execute(sql, parameters)

    def commit(self) -> None:
        self._connection.execute("RELEASE SAVEPOINT _ss_received_operation")

    def rollback(self) -> None:
        self._connection.execute("ROLLBACK TO SAVEPOINT _ss_received_operation")
        self._connection.execute("RELEASE SAVEPOINT _ss_received_operation")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


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

    @serialized_mutation
    def create_replica(self, replica_id: str, snapshot_path: str | None = None) -> str:
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
        if os.path.exists(dest):
            raise FileExistsError(f"Replica database already exists and will not be overwritten: {dest}")
        shutil.copy2(snapshot_path or self.base_db_path, dest)

        # Initialise change log and HLC
        with connect_with_foreign_keys(dest) as conn:
            conn.execute(_CHANGE_LOG_DDL)
            ensure_compaction_tables(conn)
            if snapshot_path:
                # Inherited state/log entries are part of the new replica's
                # starting snapshot; preserve operation IDs and source vectors.
                conn.execute("UPDATE _ss_change_log SET replica_id=?", (replica_id,))
                conn.execute("UPDATE _ss_compacted_receipts SET replica_id=?", (replica_id,))
            conn.commit()

        self._clocks[replica_id] = HLC(node_id=replica_id)
        return dest

    # -----------------------------------------------------------------------
    # Tracked writes
    # -----------------------------------------------------------------------

    @serialized_mutation
    def apply_change(
        self,
        replica_db_path: str,
        replica_id: str,
        table: str,
        row_id: Any,
        column: str,
        new_value: Any,
        custom_hlc: HLC | tuple[float, int] | None = None,
        bounded_bounds: tuple[int | float, int | float] | None = None,
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
        custom_hlc:
            Optional HLC instance or (ts_pt, ts_l) tuple to preserve causal timestamp.

        Returns
        -------
        str
            A UUID change_id for the log entry.

        Raises
        ------
        RuntimeError
            If the target row does not exist in the replica.
        """
        import json
        import math
        from numbers import Real
        hlc = self._clocks.setdefault(replica_id, HLC(node_id=replica_id))
        if custom_hlc is not None:
            if isinstance(custom_hlc, HLC):
                in_pt, in_l = custom_hlc.pt, custom_hlc.l
            else:
                in_pt, in_l = custom_hlc
            # Advance local clock to maintain monotonicity past the received clock
            hlc.tick(recv_pt=in_pt, recv_l=in_l)
            ts_pt, ts_l = hlc.pt, hlc.l
        else:
            hlc.tick()
            ts_pt, ts_l = hlc.pt, hlc.l

        change_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with connect_with_foreign_keys(replica_db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_change_log_table(conn)

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
            depends_on = _row_dependency_ids(conn, table, row_id)

            bounded_delta = None
            min_bound = max_bound = None
            if bounded_bounds is not None:
                min_bound, max_bound = bounded_bounds
                if any(not isinstance(value, Real) or isinstance(value, bool) for value in (old_value, new_value, min_bound, max_bound)):
                    raise ValueError("BOUNDED_SUM tracked writes require numeric current/new values and bounds.")
                if any(not math.isfinite(float(value)) for value in (old_value, new_value, min_bound, max_bound)):
                    raise ValueError("BOUNDED_SUM tracked writes require finite values and bounds.")
                if min_bound > max_bound:
                    raise ValueError("BOUNDED_SUM minimum bound must be <= maximum bound.")
                if old_value < min_bound or old_value > max_bound:
                    raise ValueError(f"BOUNDED_SUM current value {old_value} is outside [{min_bound}, {max_bound}].")
                if new_value < min_bound or new_value > max_bound:
                    raise ValueError(f"BOUNDED_SUM write {new_value} is outside inclusive bounds [{min_bound}, {max_bound}].")
                bounded_delta = new_value - old_value
                if not math.isfinite(float(bounded_delta)):
                    raise ValueError("BOUNDED_SUM signed delta must be finite.")
                # Signed deltas on one bounded cell commute.  Their replay is
                # deduplicated by origin_id, so a later local update must not
                # make an earlier delta causally dependent on it.
                depends_on = []

            # Write new value
            cursor = conn.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "{pk_col}" = ?',
                (new_value, row_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Tracked UPDATE did not affect exactly one row.")
            verify_fk_integrity(conn)
            if bounded_bounds is not None:
                if cursor.rowcount != 1:
                    raise RuntimeError("BOUNDED_SUM write did not affect exactly one row.")
                persisted = conn.execute(
                    f'SELECT "{column}" FROM "{table}" WHERE "{pk_col}" = ?',
                    (row_id,),
                ).fetchone()
                if persisted is None or persisted[0] != new_value:
                    raise RuntimeError("BOUNDED_SUM stored value differs from requested value; write rolled back.")
                stored_value = persisted[0]
                if (not isinstance(stored_value, Real) or isinstance(stored_value, bool)
                        or not math.isfinite(float(stored_value))
                        or stored_value < min_bound or stored_value > max_bound):
                    raise RuntimeError("BOUNDED_SUM stored value violates inclusive bounds; write rolled back.")

            # Log the change
            sequence = _next_change_sequence(conn)
            conn.execute(
                """
                INSERT INTO _ss_change_log
                    (id, table_name, row_id, column_name, old_value, new_value,
                     ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence, source_id, source_sequence, depends_on,
                     bounded_delta, bounds_min, bounds_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UPDATE', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    table,
                    str(row_id),
                    column,
                    str(old_value) if old_value is not None else None,
                    str(new_value) if new_value is not None else None,
                    ts_pt,
                    ts_l,
                    replica_id,
                    now_iso,
                    change_id,
                    sequence,
                    replica_id,
                    sequence,
                    json.dumps(depends_on),
                    bounded_delta,
                    min_bound,
                    max_bound,
                ),
            )
            conn.commit()

        return change_id

    @serialized_mutation
    def apply_insert(
        self,
        replica_db_path: str,
        replica_id: str,
        table: str,
        row_dict: dict[str, Any],
        custom_hlc: HLC | tuple[float, int] | None = None,
    ) -> str:
        """
        Insert a full row into a replica and record an INSERT operation in ``_ss_change_log``.
        """
        import json
        hlc = self._clocks.setdefault(replica_id, HLC(node_id=replica_id))
        if custom_hlc is not None:
            if isinstance(custom_hlc, HLC):
                in_pt, in_l = custom_hlc.pt, custom_hlc.l
            else:
                in_pt, in_l = custom_hlc
            hlc.tick(recv_pt=in_pt, recv_l=in_l)
            ts_pt, ts_l = hlc.pt, hlc.l
        else:
            hlc.tick()
            ts_pt, ts_l = hlc.pt, hlc.l

        change_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with connect_with_foreign_keys(replica_db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_change_log_table(conn)
            pk_col = self._get_pk_column(conn, table)
            if pk_col is None:
                raise RuntimeError(f"Cannot insert: table '{table}' has no single-column primary key.")

            row_id = row_dict.get(pk_col)
            cols = list(row_dict.keys())
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(f'"{c}"' for c in cols)
            values = [row_dict[c] for c in cols]
            depends_on = _row_dependency_ids(conn, table, row_id)

            sequence = _next_change_sequence(conn)
            conn.execute(
                f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})',
                values,
            )
            stored_cursor = conn.execute(f'SELECT * FROM "{table}" WHERE "{pk_col}" = ?', (row_id,))
            stored = stored_cursor.fetchone()
            stored_row = dict(zip([d[0] for d in stored_cursor.description], stored)) if stored else None
            if stored_row != row_dict:
                raise RuntimeError(f"Stored INSERT row differs from requested payload for {row_id!r} in '{table}'.")
            verify_fk_integrity(conn)

            conn.execute(
                """
                INSERT INTO _ss_change_log
                    (id, table_name, row_id, column_name, old_value, new_value,
                     ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence, source_id, source_sequence, depends_on)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'INSERT', ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    table,
                    str(row_id),
                    "*",
                    None,
                    json.dumps(stored_row, default=str),
                    ts_pt,
                    ts_l,
                    replica_id,
                    now_iso,
                    change_id,
                    sequence,
                    replica_id,
                    sequence,
                    json.dumps(depends_on),
                ),
            )
            conn.commit()

        return change_id

    @serialized_mutation
    def apply_delete(
        self,
        replica_db_path: str,
        replica_id: str,
        table: str,
        row_id: Any,
        custom_hlc: HLC | tuple[float, int] | None = None,
        origin_id: str | None = None,
    ) -> str:
        """
        Delete a row from a replica and record an explicit DELETE tombstone in ``_ss_change_log``.
        """
        import json
        hlc = self._clocks.setdefault(replica_id, HLC(node_id=replica_id))
        if custom_hlc is not None:
            if isinstance(custom_hlc, HLC):
                in_pt, in_l = custom_hlc.pt, custom_hlc.l
            else:
                in_pt, in_l = custom_hlc
            hlc.tick(recv_pt=in_pt, recv_l=in_l)
            ts_pt, ts_l = hlc.pt, hlc.l
        else:
            hlc.tick()
            ts_pt, ts_l = hlc.pt, hlc.l

        change_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with connect_with_foreign_keys(replica_db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_change_log_table(conn)
            ensure_quarantine_table(conn)
            pk_col = self._get_pk_column(conn, table)
            if pk_col is None:
                raise RuntimeError(f"Cannot delete: table '{table}' has no single-column primary key.")

            row = conn.execute(
                f'SELECT * FROM "{table}" WHERE "{pk_col}" = ?',
                (row_id,),
            ).fetchone()
            old_data = dict(zip([d[0] for d in conn.execute(f'SELECT * FROM "{table}" LIMIT 1').description], row)) if row else None
            depends_on = _row_dependency_ids(conn, table, row_id)

            # Phase 5: quarantine any child rows that would become orphaned
            quarantine_orphans(conn, parent_table=table, parent_row_id=row_id)

            sequence = _next_change_sequence(conn)

            # Enable FK enforcement; quarantine_orphans already removed children
            deleted = conn.execute(
                f'DELETE FROM "{table}" WHERE "{pk_col}" = ?',
                (row_id,),
            )
            if deleted.rowcount != 1 or conn.execute(
                f'SELECT 1 FROM "{table}" WHERE "{pk_col}" = ?', (row_id,)
            ).fetchone() is not None:
                raise RuntimeError("Tracked DELETE did not remove exactly one row.")
            # Verify no FK violations remain
            verify_fk_integrity(conn)

            conn.execute(
                """
                INSERT INTO _ss_change_log
                    (id, table_name, row_id, column_name, old_value, new_value,
                     ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence, source_id, source_sequence, depends_on)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DELETE', ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    table,
                    str(row_id),
                    "*",
                    json.dumps(old_data, default=str) if old_data else None,
                    None,
                    ts_pt,
                    ts_l,
                    replica_id,
                    now_iso,
                    origin_id or change_id,
                    sequence,
                    replica_id,
                    sequence,
                    json.dumps(depends_on),
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
        with connect_with_foreign_keys(replica_db_path) as conn:
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

    @serialized_mutation
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

        # Replay durable operations before snapshot conflict detection.
        # Expected prior state is required; divergent local history is retained
        # for normal conflict review.
        acknowledgements: list[dict[str, Any]] = []
        operations_delivered, rejected_operations = self._propagate_operations(
            (replica_a_path, replica_a_id), (replica_b_path, replica_b_id), policies=policies,
            acknowledgement_sink=acknowledgements,
        )
        reverse_delivered, reverse_rejected = self._propagate_operations(
            (replica_b_path, replica_b_id), (replica_a_path, replica_a_id), policies=policies,
            acknowledgement_sink=acknowledgements,
        )
        operations_delivered.extend(reverse_delivered)
        rejected_operations.extend(reverse_rejected)

        # 1 — detect
        # detect() returns DetectResult(conflicts, skipped_tables).
        detect_result = self._detector.detect(
            replica_a_db=replica_a_path,
            replica_b_db=replica_b_path,
            base_db=base_path,
            replica_a_id=replica_a_id,
            replica_b_id=replica_b_id,
        )
        conflicts = detect_result.conflicts
        # skipped_tables are surfaced in applied_changes metadata for observability
        skipped_tables = detect_result.skipped_tables

        applied_changes: list[dict[str, Any]] = list(operations_delivered)
        flagged_conflicts: list[str] = []
        auto_resolved = 0

        # 2 — resolve each conflict
        for conflict in conflicts:
            conflict_type = getattr(conflict, "conflict_type", "UPDATE_UPDATE")

            # ---------------------------------------------------------------
            # Row-mutation conflicts (INSERT_INSERT, UPDATE_DELETE, UNIQUE_COLLISION)
            # ---------------------------------------------------------------
            if conflict_type in ("INSERT_INSERT", "UNIQUE_COLLISION"):
                # Default safety rule: Always preserve evidence and flag for review
                self._manager.add_conflict(conflict)
                flagged_conflicts.append(conflict.conflict_id)
                continue

            elif conflict_type == "UPDATE_DELETE":
                # Handle tombstone policy: FLAG_FOR_REVIEW (default), DELETE_WINS, UPDATE_RESURRECTS
                tombstone_policy = policies.get(conflict.table, {}).get("__tombstone__", "FLAG_FOR_REVIEW")
                if tombstone_policy == "FLAG_FOR_REVIEW":
                    self._manager.add_conflict(conflict)
                    flagged_conflicts.append(conflict.conflict_id)
                    continue
                elif tombstone_policy == "DELETE_WINS":
                    # Delete wins: ensure row is deleted on both replicas.
                    ts_max = max(conflict.replica_a_ts or 0.0, conflict.replica_b_ts or 0.0)
                    pt = (ts_max // 1e6) / 1.0
                    l = int(round(ts_max % 1e6)) + 1
                    try:
                        self._write_resolved_pair(
                            replica_a_path, replica_a_id, replica_b_path, replica_b_id,
                            conflict.table, conflict.row_id, "*", None, "delete", (pt, l),
                        )
                    except Exception:
                        self._manager.add_conflict(conflict)
                        flagged_conflicts.append(conflict.conflict_id)
                    else:
                        auto_resolved += 1
                        applied_changes.append({
                            "conflict_id": conflict.conflict_id,
                            "table": conflict.table,
                            "row_id": conflict.row_id,
                            "column": "*",
                            "resolved_value": None,
                            "policy": "DELETE_WINS",
                            "explanation": "UPDATE vs DELETE resolved via DELETE_WINS tombstone policy.",
                        })
                    continue
                elif tombstone_policy == "UPDATE_RESURRECTS":
                    # The updated payload wins and is inserted/kept on both
                    winning_row = conflict.replica_a_value or conflict.replica_b_value
                    ts_max = max(conflict.replica_a_ts or 0.0, conflict.replica_b_ts or 0.0)
                    pt = (ts_max // 1e6) / 1.0
                    l = int(round(ts_max % 1e6)) + 1
                    if isinstance(winning_row, dict):
                        try:
                            self._write_resolved_pair(
                                replica_a_path, replica_a_id, replica_b_path, replica_b_id,
                                conflict.table, conflict.row_id, "*", winning_row, "upsert", (pt, l),
                            )
                        except Exception:
                            self._manager.add_conflict(conflict)
                            flagged_conflicts.append(conflict.conflict_id)
                            continue
                    else:
                        # Do not report a resolution if detection did not supply
                        # a complete row payload for the resurrection policy.
                        self._manager.add_conflict(conflict)
                        flagged_conflicts.append(conflict.conflict_id)
                        continue
                    auto_resolved += 1
                    applied_changes.append({
                        "conflict_id": conflict.conflict_id,
                        "table": conflict.table,
                        "row_id": conflict.row_id,
                        "column": "*",
                        "resolved_value": winning_row,
                        "policy": "UPDATE_RESURRECTS",
                        "explanation": "UPDATE vs DELETE resolved via UPDATE_RESURRECTS tombstone policy.",
                    })
                    continue

            # ---------------------------------------------------------------
            # Cell-level UPDATE vs UPDATE
            # ---------------------------------------------------------------
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
                bounded_bounds = None
            else:
                policy = validation.policy  # type: ignore[assignment]
                bounded_bounds = (
                    parse_bounded_sum_bounds(policy_name)
                    if policy_base_name(policy_name) == "BOUNDED_SUM" else None
                )

            resolution: ResolutionResult = self._resolver.resolve(
                policy=policy,
                base_value=conflict.base_value,
                replica_a_value=conflict.replica_a_value,
                replica_b_value=conflict.replica_b_value,
                replica_a_ts=conflict.replica_a_ts,
                replica_b_ts=conflict.replica_b_ts,
                min_bound=bounded_bounds[0] if bounded_bounds else None,
                max_bound=bounded_bounds[1] if bounded_bounds else None,
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
                # Ensure write-back timestamp strictly dominates both predecessor causal timestamps.
                # Timestamps in ConflictInfo are composite floats: pt * 1e6 + l.
                ts_a = conflict.replica_a_ts or 0.0
                ts_b = conflict.replica_b_ts or 0.0
                if ts_a > 0 or ts_b > 0:
                    # Deconstruct into (pt, l) components
                    pt_a, l_a = (ts_a // 1e6) / 1.0, int(round(ts_a % 1e6))
                    pt_b, l_b = (ts_b // 1e6) / 1.0, int(round(ts_b % 1e6))
                    max_pt = max(pt_a, pt_b)
                    max_l = max(l_a, l_b) if pt_a == pt_b else (l_a if max_pt == pt_a else l_b)
                    resolved_hlc = (max_pt, max_l + 1)
                else:
                    resolved_hlc = None

                self._write_resolved_pair(
                    replica_a_path, replica_a_id, replica_b_path, replica_b_id,
                    conflict.table, conflict.row_id, conflict.column, resolved_val,
                    "update", resolved_hlc,
                    bounded_bounds=bounded_bounds,
                    expected_values=(conflict.replica_a_value, conflict.replica_b_value) if bounded_bounds else None,
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
            skipped_tables=skipped_tables,
            rejected_operations=rejected_operations,
            acknowledgements=acknowledgements,
        )

    def _propagate_operations(
        self,
        source: tuple[str, str],
        target: tuple[str, str],
        policies: dict[str, dict[str, str]] | None = None,
        acknowledgement_sink: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Replay operations and report operations held for safety checks."""
        source_path, source_id = source
        target_path, target_id = target
        delivered: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        acknowledgements = acknowledgement_sink if acknowledgement_sink is not None else []
        with connect_with_foreign_keys(source_path) as source_conn:
            _ensure_change_log_table(source_conn)
            ensure_compaction_tables(source_conn)
            events = source_conn.execute(
                "SELECT id,table_name,row_id,column_name,old_value,new_value,op_type,"
                "origin_id,source_id,source_sequence,ts_pt,ts_l,depends_on,bounded_delta,bounds_min,bounds_max "
                "FROM _ss_change_log ORDER BY rowid"
            ).fetchall()
            known_origins = {str(e[7] or e[0]) for e in events}
            known_origins.update(str(r[0]) for r in source_conn.execute(
                "SELECT origin_id FROM _ss_compacted_receipts WHERE origin_id IS NOT NULL"
            ))
        # Batch one source's delivery under a receiver write lock. Each
        # operation still has its own savepoint, so rejected/invalid operations
        # roll back independently while successful data+receipt writes commit
        # together. A process failure rolls back the whole batch for safe retry.
        existing_receipts: dict[str, tuple[Any, ...]] = {}
        event_ids = list(dict.fromkeys(str(e[7] or e[0]) for e in events))
        with connect_with_foreign_keys(target_path) as target_conn:
            target_conn.execute("BEGIN IMMEDIATE")
            try:
                _ensure_change_log_table(target_conn)
                ensure_compaction_tables(target_conn)
                for start in range(0, len(event_ids), 400):
                    batch = event_ids[start:start + 400]
                    if not batch:
                        continue
                    placeholders = ",".join("?" for _ in batch)
                    for receipt in target_conn.execute(
                        "SELECT origin_id,table_name,row_id,column_name,op_type,bounded_delta,bounds_min,bounds_max,"
                        "old_value,new_value,source_id,source_sequence,depends_on "
                        f"FROM _ss_change_log WHERE origin_id IN ({placeholders})", batch,
                    ):
                        payload_hash = operation_payload_hash(
                            receipt[8], receipt[9], receipt[1], receipt[2], receipt[3],
                            receipt[4], receipt[10], receipt[11], receipt[12],
                            receipt[5], receipt[6], receipt[7],
                        )
                        existing_receipts[str(receipt[0])] = (tuple(receipt[1:8]), payload_hash)
                    for receipt in target_conn.execute(
                        "SELECT origin_id,table_name,row_id,column_name,op_type,bounded_delta,bounds_min,bounds_max,payload_hash "
                        f"FROM _ss_compacted_receipts WHERE origin_id IN ({placeholders})", batch,
                    ):
                        existing_receipts[str(receipt[0])] = (tuple(receipt[1:8]), receipt[8])
                for event in events:
                    (change_id, table, row_id, column, old_value, new_value, op_type,
                     origin_id, op_source, op_seq, ts_pt, ts_l, dependencies,
                     bounded_delta, bounds_min, bounds_max) = event
                    origin_id = str(origin_id or change_id)
                    op_source = str(op_source or source_id)
                    receipt = existing_receipts.get(origin_id)
                    if receipt is not None:
                        expected = (table, str(row_id), column, op_type, bounded_delta, bounds_min, bounds_max)
                        expected_hash = operation_payload_hash(
                            old_value, new_value, table, row_id, column, op_type,
                            op_source, int(op_seq or 0), dependencies,
                            bounded_delta, bounds_min, bounds_max,
                        )
                        if receipt == (expected, expected_hash):
                            acknowledgements.append({
                                "replica_id": target_id, "operation_id": origin_id,
                                "source_id": op_source, "source_sequence": int(op_seq or 0),
                                "ts_pt": float(ts_pt), "ts_l": int(ts_l),
                                "payload_hash": expected_hash,
                            })
                            continue
                        status, reason = "rejected", "operation ID was previously received with different metadata"
                    else:
                        status, reason = self._apply_received_operation(
                            target_path, target_id, table, row_id, column, old_value,
                            new_value, op_type, origin_id, op_source, int(op_seq or 0),
                            ts_pt, ts_l, known_origins, dependencies,
                            bounded_delta, bounds_min, bounds_max, policies=policies,
                            _schema_ready=True, _batch_connection=target_conn,
                        )
                    if status == "applied":
                        existing_receipts[origin_id] = (
                            table, str(row_id), column, op_type,
                            bounded_delta, bounds_min, bounds_max,
                        )
                        delivered.append({
                            "table": table, "row_id": row_id, "column": column,
                            "resolved_value": new_value, "policy": f"{op_type}_DELIVERY",
                            "operation_id": origin_id,
                            "explanation": f"Applied {op_type} from {op_source} to {target_id}.",
                        })
                        acknowledgements.append({
                            "replica_id": target_id, "operation_id": origin_id,
                            "source_id": op_source, "source_sequence": int(op_seq or 0),
                            "ts_pt": float(ts_pt), "ts_l": int(ts_l),
                            "payload_hash": operation_payload_hash(
                                old_value, new_value, table, row_id, column, op_type,
                                op_source, int(op_seq or 0), dependencies,
                                bounded_delta, bounds_min, bounds_max,
                            ),
                        })
                    elif status == "rejected":
                        rejected.append({
                            "operation_id": origin_id, "source_id": op_source,
                            "source_sequence": int(op_seq or 0), "table": table,
                            "row_id": row_id, "reason": reason,
                        })
                target_conn.commit()
            except Exception:
                target_conn.rollback()
                raise
        return delivered, rejected

    def _apply_received_operation(
        self, target_path: str, target_id: str, table: str, row_id: Any,
        column: str, old_value: str | None, new_value: str | None,
        op_type: str, origin_id: str, source_id: str, source_sequence: int,
        ts_pt: float, ts_l: int, known_origins: set[str],
        depends_on_json: str | None = None,
        bounded_delta: float | int | None = None,
        bounds_min: float | int | None = None,
        bounds_max: float | int | None = None,
        policies: dict[str, dict[str, str]] | None = None,
        _schema_ready: bool = False,
        _batch_connection: sqlite3.Connection | None = None,
    ) -> tuple[str, str | None]:
        """Atomically apply an operation, validate its result, and log receipt."""
        import json
        import math
        quote = lambda name: '"' + name.replace('"', '""') + '"'
        now_iso = datetime.now(timezone.utc).isoformat()
        connection_context = (
            connect_with_foreign_keys(target_path, timeout=10.0)
            if _batch_connection is None
            else nullcontext(_OperationSavepointConnection(_batch_connection))
        )
        with connection_context as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not _schema_ready:
                    _ensure_change_log_table(conn)
                    ensure_compaction_tables(conn)
                if self._get_pk_column(conn, table) is None:
                    conn.rollback()
                    return "rejected", "table requires a single-column primary key"
                active_receipt = conn.execute(
                    "SELECT table_name,row_id,column_name,op_type,bounded_delta,bounds_min,bounds_max,"
                    "old_value,new_value,source_id,source_sequence,depends_on "
                    "FROM _ss_change_log WHERE origin_id=? LIMIT 1", (origin_id,),
                ).fetchone()
                if active_receipt:
                    existing_metadata = tuple(active_receipt[:7])
                    existing_hash = operation_payload_hash(
                        active_receipt[7], active_receipt[8], active_receipt[0],
                        active_receipt[1], active_receipt[2], active_receipt[3],
                        active_receipt[9], active_receipt[10], active_receipt[11],
                        active_receipt[4], active_receipt[5], active_receipt[6],
                    )
                else:
                    compacted_receipt = conn.execute(
                        "SELECT table_name,row_id,column_name,op_type,bounded_delta,bounds_min,bounds_max,payload_hash "
                        "FROM _ss_compacted_receipts WHERE origin_id=? LIMIT 1", (origin_id,),
                    ).fetchone()
                    existing_metadata = tuple(compacted_receipt[:7]) if compacted_receipt else None
                    existing_hash = compacted_receipt[7] if compacted_receipt else None
                existing_receipt = (existing_metadata, existing_hash) if existing_metadata else None
                if existing_receipt:
                    expected = (table, str(row_id), column, op_type, bounded_delta, bounds_min, bounds_max)
                    expected_hash = operation_payload_hash(
                        old_value, new_value, table, row_id, column, op_type,
                        source_id, source_sequence, depends_on_json,
                        bounded_delta, bounds_min, bounds_max,
                    )
                    if existing_receipt != (expected, expected_hash):
                        conn.rollback()
                        return "rejected", "operation ID was previously received with different metadata"
                    conn.rollback()
                    return "duplicate", None
                latest_source_op = conn.execute(
                    "SELECT MAX(source_sequence) FROM ("
                    "SELECT source_sequence FROM _ss_change_log WHERE table_name=? AND row_id=? AND source_id=? "
                    "UNION ALL SELECT source_sequence FROM _ss_compacted_receipts WHERE table_name=? AND row_id=? AND source_id=?)",
                    (table, str(row_id), source_id, table, str(row_id), source_id),
                ).fetchone()[0]
                if (bounded_delta is None and latest_source_op is not None
                        and int(latest_source_op) >= source_sequence):
                    conn.rollback()
                    return "obsolete", None
                try:
                    dependencies = json.loads(depends_on_json or "[]")
                except (TypeError, ValueError):
                    conn.rollback()
                    return "rejected", "invalid dependency metadata"
                if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
                    conn.rollback()
                    return "rejected", "invalid dependency metadata"
                received = {str(r[0]) for r in conn.execute(
                    "SELECT origin_id FROM _ss_change_log WHERE origin_id IS NOT NULL UNION "
                    "SELECT origin_id FROM _ss_compacted_receipts WHERE origin_id IS NOT NULL"
                )}
                missing = sorted(set(dependencies) - received)
                if missing:
                    if op_type != "RESOLVE":
                        conn.rollback()
                        return "rejected", f"missing causal dependencies: {', '.join(missing)}"
                local_events = conn.execute(
                    "SELECT origin_id,column_name,bounded_delta,bounds_min,bounds_max "
                    "FROM _ss_change_log WHERE table_name=? AND row_id=? UNION ALL "
                    "SELECT origin_id,column_name,bounded_delta,bounds_min,bounds_max "
                    "FROM _ss_compacted_receipts WHERE table_name=? AND row_id=?",
                    (table, str(row_id), table, str(row_id)),
                ).fetchall()
                unknown_local = [
                    event for event in local_events
                    if event[0] and event[0] not in known_origins and event[0] != origin_id
                ]
                if op_type != "RESOLVE" and unknown_local:
                    bounded_compatible = (
                        bounded_delta is not None
                        and all(event[1] == column and event[2] is not None
                                and event[3] == bounds_min and event[4] == bounds_max
                                for event in unknown_local)
                    )
                    if not bounded_compatible:
                        conn.rollback()
                        return "rejected", "receiver has an operation unknown to the source"
                info = conn.execute(f'PRAGMA table_info({quote(table)})').fetchall()
                cols = [r[1] for r in info]
                pks = [r[1] for r in info if r[5] > 0]
                if len(pks) != 1 or not info:
                    conn.rollback()
                    return "rejected", "table requires a single-column primary key"
                pk = pks[0]
                row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                current = dict(zip(cols, row)) if row is not None else None

                if op_type == "INSERT":
                    payload = json.loads(new_value) if new_value else None
                    if not isinstance(payload, dict) or set(payload) != set(cols) or str(payload.get(pk)) != str(row_id):
                        conn.rollback()
                        return "rejected", "invalid or incomplete INSERT payload"
                    if current is None:
                        names = list(cols)
                        conn.execute(
                            f'INSERT INTO {quote(table)} ({", ".join(quote(c) for c in names)}) VALUES ({", ".join("?" for _ in names)})',
                            [payload[c] for c in names],
                        )
                        row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                        current = dict(zip(cols, row)) if row is not None else None
                    if current != payload:
                        conn.rollback()
                        return "rejected", "stored INSERT row does not match payload"
                elif op_type == "UPDATE":
                    if current is None or column not in current:
                        conn.rollback()
                        return "rejected", "UPDATE target row or column is missing"
                    if bounded_delta is not None:
                        numeric_metadata = (bounded_delta, bounds_min, bounds_max)
                        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
                               or not math.isfinite(float(value)) for value in numeric_metadata):
                            conn.rollback()
                            return "rejected", "BOUNDED_SUM operation has invalid numeric metadata"
                        if bounds_min > bounds_max:
                            conn.rollback()
                            return "rejected", "BOUNDED_SUM operation has inverted bounds"
                        current_value = current[column]
                        if not isinstance(current_value, (int, float)) or isinstance(current_value, bool):
                            conn.rollback()
                            return "rejected", "BOUNDED_SUM target value is not numeric"
                        if current_value < bounds_min or current_value > bounds_max:
                            conn.rollback()
                            return "rejected", f"BOUNDED_SUM target value {current_value} is outside [{bounds_min}, {bounds_max}]"
                        candidate = current_value + bounded_delta
                        if candidate < bounds_min or candidate > bounds_max:
                            conn.rollback()
                            return "rejected", (
                                f"BOUNDED_SUM pending: applying signed delta {bounded_delta:+} "
                                f"would produce {candidate} outside inclusive bounds [{bounds_min}, {bounds_max}]"
                            )
                        if isinstance(current_value, int) and isinstance(bounded_delta, int):
                            candidate = int(candidate)
                        cursor = conn.execute(
                            f'UPDATE {quote(table)} SET {quote(column)}=? WHERE {quote(pk)}=?',
                            (candidate, row_id),
                        )
                        if cursor.rowcount != 1:
                            conn.rollback()
                            return "rejected", "BOUNDED_SUM update did not affect exactly one row"
                        row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                        current = dict(zip(cols, row)) if row is not None else None
                        if current is None or current[column] != candidate:
                            conn.rollback()
                            return "rejected", "stored BOUNDED_SUM value differs from the computed candidate"
                    else:
                        old_matches = (current[column] is None and old_value is None) or str(current[column]) == old_value
                        new_typed = new_value
                        if current[column] is not None and new_value is not None:
                            if isinstance(current[column], int): new_typed = int(new_value)
                            elif isinstance(current[column], float): new_typed = float(new_value)
                        if not old_matches and current[column] != new_typed:
                            conn.rollback()
                            return "rejected", "UPDATE prior value does not match receiver"
                        if old_matches:
                            cursor = conn.execute(f'UPDATE {quote(table)} SET {quote(column)}=? WHERE {quote(pk)}=?', (new_typed, row_id))
                            if cursor.rowcount != 1:
                                conn.rollback()
                                return "rejected", "UPDATE did not affect exactly one row"
                            row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                            current = dict(zip(cols, row)) if row is not None else None
                        if current is None or current[column] != new_typed:
                            conn.rollback()
                            return "rejected", "stored UPDATE value does not match operation"
                elif op_type == "DELETE":
                    expected = json.loads(old_value) if old_value else None
                    if current is not None and current != expected:
                        conn.rollback()
                        return "rejected", "DELETE prior row does not match receiver"
                    if current is not None:
                        # Phase 5: quarantine orphaned children before enforcing FK delete
                        ensure_quarantine_table(conn)
                        quarantine_orphans(conn, parent_table=table, parent_row_id=row_id)
                        cursor = conn.execute(f'DELETE FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,))
                        if cursor.rowcount != 1 or conn.execute(f'SELECT 1 FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone():
                            conn.rollback()
                            return "rejected", "stored DELETE row remains present"
                        try:
                            verify_fk_integrity(conn)
                        except Exception as fk_err:
                            conn.rollback()
                            return "rejected", f"FK integrity violation after DELETE: {fk_err}"
                elif op_type == "RESOLVE":
                    expected_rows = json.loads(old_value) if old_value else {}
                    payload = json.loads(new_value) if new_value else None
                    if not isinstance(expected_rows, dict) or not isinstance(payload, dict):
                        conn.rollback()
                        return "rejected", "invalid RESOLVE payload"
                    kind = payload.get("kind")
                    if kind == "cell":
                        name, value = payload.get("column"), payload.get("value")
                        bounded = payload.get("bounds")

                        # Determine whether this column is governed by BOUNDED_SUM
                        expected_bounds: tuple[int | float, int | float] | None = None
                        col_policy = (policies or {}).get(table, {}).get(name)
                        if col_policy and policy_base_name(col_policy) == "BOUNDED_SUM":
                            try:
                                expected_bounds = parse_bounded_sum_bounds(col_policy)
                            except ValueError as exc:
                                conn.rollback()
                                return "rejected", f"invalid policy bounds for {table}.{name}: {exc}"
                        elif bounds_min is not None and bounds_max is not None:
                            expected_bounds = (bounds_min, bounds_max)
                        else:
                            row_b = conn.execute(
                                "SELECT bounds_min, bounds_max FROM _ss_change_log "
                                "WHERE table_name=? AND column_name=? AND bounds_min IS NOT NULL LIMIT 1",
                                (table, str(name)),
                            ).fetchone()
                            if row_b and row_b[0] is not None and row_b[1] is not None:
                                expected_bounds = (row_b[0], row_b[1])

                        if expected_bounds is not None:
                            if bounded is None:
                                conn.rollback()
                                return "rejected", "RESOLVE on BOUNDED_SUM column requires bounds metadata"
                            min_b = bounded.get("min") if isinstance(bounded, dict) else None
                            max_b = bounded.get("max") if isinstance(bounded, dict) else None
                            if min_b != expected_bounds[0] or max_b != expected_bounds[1]:
                                conn.rollback()
                                return "rejected", (
                                    f"RESOLVE bounds [{min_b}, {max_b}] do not match "
                                    f"policy bounds [{expected_bounds[0]}, {expected_bounds[1]}]"
                                )

                        if bounded is not None:
                            minimum = bounded.get("min") if isinstance(bounded, dict) else None
                            maximum = bounded.get("max") if isinstance(bounded, dict) else None
                            bounded_values = (value, minimum, maximum)
                            if (name is None or any(
                                    not isinstance(item, (int, float)) or isinstance(item, bool)
                                    or not math.isfinite(float(item)) for item in bounded_values
                                ) or minimum > maximum or value < minimum or value > maximum):
                                conn.rollback()
                                return "rejected", "RESOLVE BOUNDED_SUM value violates its inclusive bounds"
                        allowed = [r.get(name) for r in expected_rows.values() if isinstance(r, dict)]
                        if current is None or name not in current or (current[name] != value and current[name] not in allowed):
                            conn.rollback()
                            return "rejected", "RESOLVE cell prior value does not match receiver"
                        if current[name] != value:
                            cursor = conn.execute(f'UPDATE {quote(table)} SET {quote(name)}=? WHERE {quote(pk)}=?', (value, row_id))
                            if cursor.rowcount != 1:
                                conn.rollback()
                                return "rejected", "RESOLVE cell update failed"
                        row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                        current = dict(zip(cols, row)) if row is not None else None
                        if current is None or current[name] != value:
                            conn.rollback()
                            return "rejected", "stored RESOLVE cell differs from payload"
                    elif kind == "row":
                        payload_row = payload.get("value")
                        allowed = [r for r in expected_rows.values() if isinstance(r, dict)]
                        if not isinstance(payload_row, dict) or set(payload_row) != set(cols) or str(payload_row.get(pk)) != str(row_id):
                            conn.rollback()
                            return "rejected", "invalid RESOLVE row payload"
                        if current != payload_row and current not in allowed:
                            conn.rollback()
                            return "rejected", "RESOLVE row prior value does not match receiver"
                        if current != payload_row:
                            names = list(cols)
                            mutable = [c for c in names if c != pk]
                            conflict = "DO UPDATE SET " + ", ".join(
                                f'{quote(c)}=excluded.{quote(c)}' for c in mutable
                            ) if mutable else "DO NOTHING"
                            sql = f'INSERT INTO {quote(table)} ({", ".join(quote(c) for c in names)}) VALUES ({", ".join("?" for _ in names)}) ON CONFLICT ({quote(pk)}) {conflict}'
                            conn.execute(sql, [payload_row[c] for c in names])
                        row = conn.execute(f'SELECT * FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone()
                        current = dict(zip(cols, row)) if row is not None else None
                        if current != payload_row:
                            conn.rollback()
                            return "rejected", "stored RESOLVE row differs from payload"
                    elif kind == "delete":
                        allowed = [r for r in expected_rows.values() if isinstance(r, dict)]
                        if current is not None and current not in allowed:
                            conn.rollback()
                            return "rejected", "RESOLVE delete prior row does not match receiver"
                        if current is not None:
                            cursor = conn.execute(f'DELETE FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,))
                            if cursor.rowcount != 1 or conn.execute(f'SELECT 1 FROM {quote(table)} WHERE {quote(pk)}=?', (row_id,)).fetchone():
                                conn.rollback()
                                return "rejected", "stored RESOLVE delete row remains present"
                    else:
                        conn.rollback()
                        return "rejected", "unknown RESOLVE operation kind"
                else:
                    conn.rollback()
                    return "rejected", f"unsupported operation type: {op_type}"

                try:
                    verify_fk_integrity(conn)
                except sqlite3.IntegrityError as fk_err:
                    conn.rollback()
                    return "rejected", f"foreign-key integrity violation: {fk_err}"

                receipt_min = bounds_min if bounds_min is not None else (
                    bounded.get("min") if (op_type == "RESOLVE" and isinstance(bounded, dict)) else None
                )
                receipt_max = bounds_max if bounds_max is not None else (
                    bounded.get("max") if (op_type == "RESOLVE" and isinstance(bounded, dict)) else None
                )
                local_sequence = _next_change_sequence(conn)
                conn.execute(
                    """INSERT INTO _ss_change_log
                    (id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,applied_at,op_type,origin_id,sequence,source_id,source_sequence,depends_on,bounded_delta,bounds_min,bounds_max)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), table, str(row_id), column, old_value, new_value,
                     ts_pt, ts_l, target_id, now_iso, op_type, origin_id,
                     local_sequence, source_id, source_sequence, json.dumps(dependencies),
                     bounded_delta, receipt_min, receipt_max),
                )
                stored_receipt = conn.execute(
                    "SELECT table_name,row_id,column_name,op_type,bounded_delta,bounds_min,bounds_max,"
                    "old_value,new_value,source_id,source_sequence,depends_on "
                    "FROM _ss_change_log WHERE origin_id=?", (origin_id,),
                ).fetchone()
                expected_receipt_hash = operation_payload_hash(
                    old_value, new_value, table, row_id, column, op_type,
                    source_id, source_sequence, depends_on_json,
                    bounded_delta, receipt_min, receipt_max,
                )
                actual_receipt_hash = operation_payload_hash(
                    stored_receipt[7], stored_receipt[8], stored_receipt[0],
                    stored_receipt[1], stored_receipt[2], stored_receipt[3],
                    stored_receipt[9], stored_receipt[10], stored_receipt[11],
                    stored_receipt[4], stored_receipt[5], stored_receipt[6],
                ) if stored_receipt else None
                if actual_receipt_hash != expected_receipt_hash:
                    conn.rollback()
                    return "rejected", "stored operation receipt differs from the delivered payload"
                conn.commit()
                return "applied", None
            except sqlite3.IntegrityError as integrity_err:
                conn.rollback()
                if "foreign key constraint failed" in str(integrity_err).casefold():
                    return "rejected", f"SQLite foreign-key constraint rejected operation: {integrity_err}"
                raise
            except Exception:
                conn.rollback()
                raise

    def _apply_received_tombstone(
        self,
        target_path: str,
        target_id: str,
        table: str,
        row_id: str,
        deleted_row: dict[str, Any],
        origin_id: str,
    ) -> bool:
        """Atomically validate, delete, and log a received tombstone."""
        import json

        now_iso = datetime.now(timezone.utc).isoformat()
        hlc = self._clocks.setdefault(target_id, HLC(node_id=target_id)).tick()
        with connect_with_foreign_keys(target_path, timeout=10.0) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _ensure_change_log_table(conn)
                pk_col = self._get_pk_column(conn, table)
                if pk_col is None:
                    conn.rollback()
                    return False

                duplicate = conn.execute(
                    "SELECT 1 FROM _ss_change_log WHERE origin_id = ? LIMIT 1",
                    (origin_id,),
                ).fetchone()
                if duplicate:
                    conn.rollback()
                    return False

                local_mutation = conn.execute(
                    "SELECT 1 FROM _ss_change_log WHERE replica_id = ? "
                    "AND table_name = ? AND row_id = ? LIMIT 1",
                    (target_id, table, str(row_id)),
                ).fetchone()
                if local_mutation:
                    conn.rollback()
                    return False

                columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
                if not columns or set(deleted_row) != set(columns):
                    conn.rollback()
                    return False
                row = conn.execute(
                    f'SELECT * FROM "{table}" WHERE "{pk_col}" = ?', (row_id,)
                ).fetchone()
                if row is None or dict(zip(columns, row)) != deleted_row:
                    conn.rollback()
                    return False

                ensure_quarantine_table(conn)
                quarantine_orphans(conn, table, row_id)
                cursor = conn.execute(
                    f'DELETE FROM "{table}" WHERE "{pk_col}" = ?', (row_id,)
                )
                if cursor.rowcount != 1 or conn.execute(
                    f'SELECT 1 FROM "{table}" WHERE "{pk_col}" = ?', (row_id,)
                ).fetchone() is not None:
                    conn.rollback()
                    return False
                verify_fk_integrity(conn)
                local_change_id = str(uuid.uuid4())
                conn.execute(
                """INSERT INTO _ss_change_log
                       (id, table_name, row_id, column_name, old_value, new_value,
                        ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence)
                       VALUES (?, ?, ?, '*', ?, NULL, ?, ?, ?, ?, 'DELETE', ?, ?)""",
                    (local_change_id, table, str(row_id), json.dumps(deleted_row, default=str),
                     hlc.pt, hlc.l, target_id, now_iso, origin_id, _next_change_sequence(conn)),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_pk_column(conn: sqlite3.Connection, table: str) -> str | None:
        pragma = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        pks = [row[1] for row in pragma if row[5] > 0]   # all PK participants
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

    def _write_resolved_pair(
        self,
        replica_a_path: str,
        replica_a_id: str,
        replica_b_path: str,
        replica_b_id: str,
        table: str,
        row_id: Any,
        column: str,
        value: Any,
        operation: str,
        custom_hlc: HLC | tuple[float, int] | None = None,
        bounded_bounds: tuple[int | float, int | float] | None = None,
        expected_values: tuple[Any, Any] | None = None,
    ) -> None:
        """Apply one resolution to both replica files in a single transaction."""
        import json
        import os

        if os.path.normcase(os.path.realpath(replica_a_path)) == os.path.normcase(
            os.path.realpath(replica_b_path)
        ):
            raise RuntimeError("Cannot resolve a conflict across the same replica database twice.")

        def quote(identifier: str) -> str:
            return '"' + identifier.replace('"', '""') + '"'

        with connect_with_foreign_keys(replica_a_path, timeout=10.0) as conn:
            conn.execute("ATTACH DATABASE ? AS replica_b", (replica_b_path,))
            ensure_quarantine_table(conn, "main")
            ensure_quarantine_table(conn, "replica_b")
            modes = [
                conn.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0].lower()
                for schema in ("main", "replica_b")
            ]
            if any(mode == "wal" for mode in modes):
                raise RuntimeError("Atomic pair resolution requires rollback-journal SQLite databases.")
            conn.execute("BEGIN IMMEDIATE")
            schemas = ("main", "replica_b")
            replica_ids = {"main": replica_a_id, "replica_b": replica_b_id}
            table_info: dict[str, list[tuple[Any, ...]]] = {}
            for schema in schemas:
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
                for col, ddl in (("op_type", "TEXT NOT NULL DEFAULT 'UPDATE'"),
                                 ("origin_id", "TEXT"), ("sequence", "INTEGER"),
                                 ("source_id", "TEXT"), ("source_sequence", "INTEGER"),
                                 ("depends_on", "TEXT NOT NULL DEFAULT '[]'"),
                                 ("bounded_delta", "NUMERIC"),
                                 ("bounds_min", "NUMERIC"),
                                 ("bounds_max", "NUMERIC")):
                    if col not in log_cols:
                        conn.execute(f"ALTER TABLE {schema}._ss_change_log ADD COLUMN {col} {ddl}")
                # Pair resolution runs once per conflict. Restrict legacy
                # backfills to schema upgrades so each conflict does not scan
                # both complete change logs before writing its resolution.
                if "sequence" not in log_cols:
                    conn.execute(
                        f"UPDATE {schema}._ss_change_log SET sequence = rowid WHERE sequence IS NULL"
                    )
                if "origin_id" not in log_cols:
                    conn.execute(f"UPDATE {schema}._ss_change_log SET origin_id=id WHERE origin_id IS NULL OR origin_id='' ")
                if "source_id" not in log_cols:
                    conn.execute(f"UPDATE {schema}._ss_change_log SET source_id=replica_id WHERE source_id IS NULL OR source_id='' ")
                if "source_sequence" not in log_cols:
                    conn.execute(f"UPDATE {schema}._ss_change_log SET source_sequence=sequence WHERE source_sequence IS NULL")
                ensure_compaction_tables(conn, schema)
                conn.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {schema}._ss_change_log_sequence_idx "
                    "ON _ss_change_log(sequence)"
                )
                info = conn.execute(f"PRAGMA {schema}.table_info({quote(table)})").fetchall()
                pks = [r[1] for r in info if r[5] > 0]
                if not info or len(pks) != 1:
                    raise RuntimeError(f"Cannot resolve '{table}': single-column primary key required.")
                table_info[schema] = info

            pk_cols = {
                schema: next(r[1] for r in table_info[schema] if r[5] > 0)
                for schema in schemas
            }
            if pk_cols["main"] != pk_cols["replica_b"]:
                raise RuntimeError(f"Primary-key schemas differ for '{table}'.")
            pk_col = pk_cols["main"]
            if custom_hlc is None:
                clock_values = {}
                for replica_id in (replica_a_id, replica_b_id):
                    clock = self._clocks.setdefault(replica_id, HLC(node_id=replica_id)).tick()
                    clock_values[replica_id] = (clock.pt, clock.l)
            else:
                if isinstance(custom_hlc, HLC):
                    received = (custom_hlc.pt, custom_hlc.l)
                else:
                    received = custom_hlc
                clock_values = {}
                for replica_id in (replica_a_id, replica_b_id):
                    clock = self._clocks.setdefault(replica_id, HLC(node_id=replica_id))
                    clock.tick(recv_pt=received[0], recv_l=received[1])
                    clock_values[replica_id] = (clock.pt, clock.l)

            operation_id = str(uuid.uuid4())
            resolution_source_id = "resolution:" + ":".join(sorted((replica_a_id, replica_b_id)))
            resolution_sequence = max(
                int(conn.execute(
                    f"SELECT COALESCE(MAX(source_sequence),0) FROM ("
                    f"SELECT source_sequence FROM {schema}._ss_change_log WHERE source_id=? UNION ALL "
                    f"SELECT source_sequence FROM {schema}._ss_compacted_receipts WHERE source_id=?)",
                    (resolution_source_id, resolution_source_id),
                ).fetchone()[0])
                for schema in schemas
            ) + 1
            now_iso = datetime.now(timezone.utc).isoformat()

            def read_row(schema: str) -> dict[str, Any] | None:
                cols = [r[1] for r in table_info[schema]]
                row = conn.execute(
                    f"SELECT * FROM {schema}.{quote(table)} WHERE {quote(pk_col)} = ?",
                    (row_id,),
                ).fetchone()
                return dict(zip(cols, row)) if row is not None else None

            old_snapshots = {replica_ids[schema]: read_row(schema) for schema in schemas}
            dependencies = sorted({
                dep for schema in schemas
                for dep in _row_dependency_ids(conn, table, row_id, schema)
            })
            if operation == "delete":
                resolution_payload = {"kind": "delete"}
            elif operation == "upsert":
                resolution_payload = {"kind": "row", "value": value}
            else:
                resolution_payload = {"kind": "cell", "column": column, "value": value}
                if bounded_bounds is not None:
                    resolution_payload["bounds"] = {"min": bounded_bounds[0], "max": bounded_bounds[1]}

            def log_resolution(schema: str) -> None:
                sequence = conn.execute(
                    f"SELECT COALESCE(MAX(sequence),0)+1 FROM ("
                    f"SELECT sequence FROM {schema}._ss_change_log UNION ALL "
                    f"SELECT sequence FROM {schema}._ss_compacted_receipts)"
                ).fetchone()[0]
                ts_pt, ts_l = clock_values[replica_ids[schema]]
                res_min = bounded_bounds[0] if bounded_bounds is not None else None
                res_max = bounded_bounds[1] if bounded_bounds is not None else None
                conn.execute(
                    f"""INSERT INTO {schema}._ss_change_log
                        (id, table_name, row_id, column_name, old_value, new_value,
                         ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence,
                         source_id, source_sequence, depends_on, bounded_delta, bounds_min, bounds_max)
                        VALUES (?, ?, ?, '*', ?, ?, ?, ?, ?, ?, 'RESOLVE', ?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (str(uuid.uuid4()), table, str(row_id),
                     json.dumps(old_snapshots, default=str), json.dumps(resolution_payload, default=str),
                     ts_pt, ts_l, replica_ids[schema], now_iso, operation_id, sequence,
                     resolution_source_id, resolution_sequence, json.dumps(dependencies),
                     res_min, res_max),
                )

            for schema in schemas:
                old_row = read_row(schema)
                if operation == "delete":
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
                        raise RuntimeError(f"Delete resolution did not remove row {row_id!r} from {schema}.")
                    log_resolution(schema)
                elif operation == "upsert":
                    if not isinstance(value, dict) or value.get(pk_col) != row_id:
                        raise RuntimeError("Resolved row payload must contain the conflict primary key.")
                    cols = list(value)
                    valid_cols = {r[1] for r in table_info[schema]}
                    if set(cols) != valid_cols:
                        raise RuntimeError(f"Resolved row payload must include every column in '{table}'.")
                    update_cols = [col for col in cols if col != pk_col]
                    conflict_sql = (
                        "DO UPDATE SET " + ", ".join(
                            f"{quote(col)} = excluded.{quote(col)}" for col in update_cols
                        )
                        if update_cols else "DO NOTHING"
                    )
                    conn.execute(
                        f"INSERT INTO {schema}.{quote(table)} "
                        f"({', '.join(quote(col) for col in cols)}) "
                        f"VALUES ({', '.join('?' for _ in cols)}) "
                        f"ON CONFLICT ({quote(pk_col)}) {conflict_sql}",
                        [value[col] for col in cols],
                    )
                    persisted = read_row(schema)
                    if persisted != value:
                        raise RuntimeError(f"Resolved row payload was not fully applied in {schema}.")
                    log_resolution(schema)
                elif operation == "update":
                    if old_row is None:
                        raise RuntimeError(f"Cannot resolve missing row {row_id!r} in {schema}.")
                    if column not in {r[1] for r in table_info[schema]}:
                        raise RuntimeError(f"Column '{column}' is missing from '{table}'.")
                    if expected_values is not None:
                        expected = expected_values[0] if schema == "main" else expected_values[1]
                        if old_row.get(column) != expected:
                            raise RuntimeError(
                                f"BOUNDED_SUM row changed after detection in {schema}; refusing stale materialization."
                            )
                    if bounded_bounds is not None and not bounded_bounds[0] <= value <= bounded_bounds[1]:
                        raise RuntimeError("BOUNDED_SUM materialization is outside inclusive bounds.")
                    cursor = conn.execute(
                        f"UPDATE {schema}.{quote(table)} SET {quote(column)} = ? "
                        f"WHERE {quote(pk_col)} = ?",
                        (value, row_id),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(f"Resolution did not update exactly one row in {schema}.")
                    persisted = read_row(schema)
                    if persisted is None or persisted.get(column) != value:
                        raise RuntimeError(f"Resolution did not persist the chosen value in {schema}.")
                    log_resolution(schema)
                else:
                    raise ValueError(f"Unsupported resolution operation: {operation}")
                verify_fk_integrity(conn, schema)
            conn.commit()
