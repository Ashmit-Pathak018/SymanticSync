"""
conflict_detector.py
--------------------
Detects concurrent divergences (true conflicts) across three SQLite database
replicas: *replica_a*, *replica_b*, and a shared *base* snapshot.

A **conflict** is defined as: both replica_a AND replica_b have changed the
same cell relative to the base value.  If only one replica has changed, it is
a clean update (no conflict).

Timestamps are read from the ``_ss_change_log`` metadata table written by
``CRDTSyncEngine``.  If that table is absent, ``time.time()`` is used as a
fallback so the detector remains functional on bare databases.

Causality
---------
This implementation uses a **state-based** (snapshot-diff) detection model.
It does NOT automatically classify UPDATE vs DELETE operations as causally
ordered or concurrent based solely on HLC timestamps; doing so would require
a vector clock or explicit causal dependency tracking that is beyond the
current scope.

Instead, timestamps from ``_ss_change_log`` are **recorded in the conflict
record** (``replica_a_ts``, ``replica_b_ts``) so that callers — human
reviewers or policy engines — can inspect them when deciding how to resolve.

Cases 3 and 4 (A updates + B deletes, or A deletes + B updates) always
emit a conflict when detected from state alone, because the system cannot
safely distinguish a causally ordered deletion from a concurrent one without
a full causal history. This is documented in KNOWN_LIMITATIONS.md.

Composite-PK tables
-------------------
Tables whose primary key spans more than one column (``pk`` value in PRAGMA
ranges from 1..N where N > 1) cannot be addressed by a single row_id scalar.
Such tables are recorded in ``DetectResult.skipped_tables`` rather than
silently ignored, so callers can surface the limitation to the user.

UPDATE timestamp key
--------------------
``apply_change`` (UPDATE) writes ``column_name = <actual_column>`` to the
change log.  Only ``apply_delete`` and ``apply_insert`` write
``column_name = '*'``.  The helper ``_get_row_update_ts`` scans all
non-PK columns to find the earliest UPDATE timestamp for a row, which is
more accurate than looking up the ``"*"`` key (which would miss UPDATEs).
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, NamedTuple


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConflictInfo:
    """Describes a detected conflict across replicas (column or row-mutation level)."""
    conflict_id: str                  # UUID4 string
    table: str
    row_id: Any                       # Primary key value
    column: str                       # Column name or '*' for row-level conflicts
    base_value: Any                   # Base cell value or full row dict (None for INSERTs)
    replica_a_value: Any              # Replica A cell value or full row dict
    replica_b_value: Any              # Replica B cell value or full row dict
    replica_a_id: str
    replica_b_id: str
    replica_a_ts: float               # HLC or wall-clock timestamp
    replica_b_ts: float
    detected_at: str                  # ISO-8601 UTC
    conflict_type: str = "UPDATE_UPDATE"  # UPDATE_UPDATE, INSERT_INSERT, UPDATE_DELETE, UNIQUE_COLLISION
    status: str = "pending"           # pending, resolved, flagged
    resolution_mode: Any = None       # auto, pick_a, pick_b, custom
    resolved_value: Any = None
    explanation: Any = None


class DetectResult(NamedTuple):
    """
    Return type for ``ConflictDetector.detect()``.

    Attributes
    ----------
    conflicts:
        List of all detected concurrent conflicts.
    skipped_tables:
        Table names that could not be processed because they have no
        single-column primary key (composite-PK or no PK at all).
        Callers should surface these to the user rather than silently
        ignoring them.
    """
    conflicts: list[ConflictInfo]
    skipped_tables: list[str]


# ---------------------------------------------------------------------------
# ConflictDetector
# ---------------------------------------------------------------------------

class ConflictDetector:
    """
    Performs three-way diff across base, replica_a, and replica_b SQLite files.

    The detector is schema-agnostic: it discovers tables and columns
    dynamically using ``PRAGMA table_info``.
    """

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def detect(
        self,
        replica_a_db: str,
        replica_b_db: str,
        base_db: str,
        replica_a_id: str,
        replica_b_id: str,
    ) -> DetectResult:
        """
        Detect all divergences between two replicas relative to base.

        Parameters
        ----------
        replica_a_db:
            Path to the replica A SQLite database file.
        replica_b_db:
            Path to the replica B SQLite database file.
        base_db:
            Path to the common ancestor (base) SQLite database file.
        replica_a_id:
            Logical identifier string for replica A.
        replica_b_id:
            Logical identifier string for replica B.

        Returns
        -------
        DetectResult
            A named tuple with two fields:

            - ``conflicts``: all cells / rows where both replicas diverged.
            - ``skipped_tables``: tables with composite or absent primary keys
              that could not be processed; callers must surface these.
        """
        conflicts: list[ConflictInfo] = []
        skipped_tables: list[str] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        with (
            self._connect(base_db) as base_conn,
            self._connect(replica_a_db) as conn_a,
            self._connect(replica_b_db) as conn_b,
        ):
            # Build timestamp and op-type lookup tables from change logs (if present)
            ts_a = self._build_ts_map(conn_a, replica_a_id)
            ts_b = self._build_ts_map(conn_b, replica_b_id)
            op_a = self._build_op_map(conn_a, replica_a_id)
            op_b = self._build_op_map(conn_b, replica_b_id)

            # Discover all user tables across base, A, and B
            all_tables = sorted(
                set(self._list_user_tables(base_conn))
                | set(self._list_user_tables(conn_a))
                | set(self._list_user_tables(conn_b))
            )

            for table in all_tables:
                # Find pk column — returns None for composite or absent PK
                pk_col = (
                    self._get_pk_column(base_conn, table)
                    or self._get_pk_column(conn_a, table)
                    or self._get_pk_column(conn_b, table)
                )
                if pk_col is None:
                    # Tables without a single-column PK cannot be addressed.
                    # Surface explicitly so callers can report the limitation.
                    skipped_tables.append(table)
                    continue

                columns = (
                    self._get_column_names(base_conn, table)
                    or self._get_column_names(conn_a, table)
                    or self._get_column_names(conn_b, table)
                )
                non_pk_cols = [c for c in columns if c != pk_col]

                # Fetch all rows from all three sides
                base_rows = (
                    self._fetch_rows(base_conn, table, pk_col, columns)
                    if self._table_exists(base_conn, table) else {}
                )
                rows_a = (
                    self._fetch_rows(conn_a, table, pk_col, columns)
                    if self._table_exists(conn_a, table) else {}
                )
                rows_b = (
                    self._fetch_rows(conn_b, table, pk_col, columns)
                    if self._table_exists(conn_b, table) else {}
                )

                all_row_ids = (
                    set(base_rows.keys()) | set(rows_a.keys()) | set(rows_b.keys())
                )

                for row_id in all_row_ids:
                    in_base = row_id in base_rows
                    in_a = row_id in rows_a
                    in_b = row_id in rows_b

                    base_row = base_rows.get(row_id)
                    row_a = rows_a.get(row_id)
                    row_b = rows_b.get(row_id)

                    # Row-level tombstone key (DELETE/INSERT ops use column_name='*')
                    ts_key_row = (table, str(row_id), "*")

                    # -----------------------------------------------------------
                    # Case 1: Row in base, exists in both A and B -> UPDATE vs UPDATE
                    # -----------------------------------------------------------
                    if in_base and in_a and in_b:
                        for col in non_pk_cols:
                            base_val = base_row.get(col)
                            val_a = row_a.get(col)
                            val_b = row_b.get(col)

                            a_changed = not self._values_equal(val_a, base_val)
                            b_changed = not self._values_equal(val_b, base_val)

                            if a_changed and b_changed and not self._values_equal(val_a, val_b):
                                ts_key = (table, str(row_id), col)
                                conflicts.append(
                                    ConflictInfo(
                                        conflict_id=str(uuid.uuid4()),
                                        table=table,
                                        row_id=row_id,
                                        column=col,
                                        conflict_type="UPDATE_UPDATE",
                                        base_value=base_val,
                                        replica_a_value=val_a,
                                        replica_b_value=val_b,
                                        replica_a_id=replica_a_id,
                                        replica_b_id=replica_b_id,
                                        # UPDATE writes actual column key; fall back to row key
                                        replica_a_ts=ts_a.get(ts_key, ts_a.get(ts_key_row, time.time())),
                                        replica_b_ts=ts_b.get(ts_key, ts_b.get(ts_key_row, time.time())),
                                        detected_at=now_iso,
                                        status="pending",
                                    )
                                )

                    # -----------------------------------------------------------
                    # Case 2: Row NOT in base, inserted in both A and B
                    # -> INSERT vs INSERT (PK collision)
                    # -----------------------------------------------------------
                    elif not in_base and in_a and in_b:
                        rows_identical = all(
                            self._values_equal(row_a.get(c), row_b.get(c)) for c in columns
                        )
                        if not rows_identical:
                            conflicts.append(
                                ConflictInfo(
                                    conflict_id=str(uuid.uuid4()),
                                    table=table,
                                    row_id=row_id,
                                    column="*",
                                    conflict_type="INSERT_INSERT",
                                    base_value=None,
                                    replica_a_value=dict(row_a),
                                    replica_b_value=dict(row_b),
                                    replica_a_id=replica_a_id,
                                    replica_b_id=replica_b_id,
                                    replica_a_ts=ts_a.get(ts_key_row, time.time()),
                                    replica_b_ts=ts_b.get(ts_key_row, time.time()),
                                    detected_at=now_iso,
                                    status="flagged",
                                    explanation=(
                                        f"INSERT collision on PK {row_id!r} with divergent row payloads."
                                    ),
                                )
                            )

                    # -----------------------------------------------------------
                    # Case 3: Row in base, present in A but missing in B.
                    #
                    # B deleted the row (or B is stale and never received it).
                    # If A mutated the row → flag as UPDATE_DELETE.
                    # If A did not mutate → clean single-sided delete, no conflict.
                    #
                    # Timestamps are recorded in the conflict for reviewer context.
                    # This implementation does NOT auto-exempt based on HLC ordering;
                    # see module docstring for the causality limitation.
                    # -----------------------------------------------------------
                    elif in_base and in_a and not in_b:
                        a_mutated = any(
                            not self._values_equal(row_a.get(c), base_row.get(c))
                            for c in non_pk_cols
                        )
                        if a_mutated:
                            # Record the best available timestamps for reviewer context.
                            ts_a_update = self._get_row_update_ts(ts_a, table, str(row_id), non_pk_cols)
                            ts_b_delete = ts_b.get(ts_key_row, 0.0)
                            b_last_op = op_b.get((table, str(row_id)), "unknown")
                            conflicts.append(
                                ConflictInfo(
                                    conflict_id=str(uuid.uuid4()),
                                    table=table,
                                    row_id=row_id,
                                    column="*",
                                    conflict_type="UPDATE_DELETE",
                                    base_value=dict(base_row),
                                    replica_a_value=dict(row_a),
                                    replica_b_value=None,  # B deleted
                                    replica_a_id=replica_a_id,
                                    replica_b_id=replica_b_id,
                                    replica_a_ts=(
                                        ts_a_update if ts_a_update > 0.0
                                        else ts_a.get(ts_key_row, time.time())
                                    ),
                                    replica_b_ts=(
                                        ts_b_delete if ts_b_delete > 0.0
                                        else time.time()
                                    ),
                                    detected_at=now_iso,
                                    status="flagged",
                                    explanation=(
                                        f"Concurrent UPDATE vs DELETE: "
                                        f"Replica {replica_a_id} modified row, "
                                        f"Replica {replica_b_id} deleted row "
                                        f"(last op on B: {b_last_op})."
                                    ),
                                )
                            )
                        # else: A has base-equal value, B deleted → clean delete, no conflict.

                    # -----------------------------------------------------------
                    # Case 4: Row in base, present in B but missing in A.
                    # (Mirror of Case 3.)
                    # -----------------------------------------------------------
                    elif in_base and not in_a and in_b:
                        b_mutated = any(
                            not self._values_equal(row_b.get(c), base_row.get(c))
                            for c in non_pk_cols
                        )
                        if b_mutated:
                            ts_b_update = self._get_row_update_ts(ts_b, table, str(row_id), non_pk_cols)
                            ts_a_delete = ts_a.get(ts_key_row, 0.0)
                            a_last_op = op_a.get((table, str(row_id)), "unknown")
                            conflicts.append(
                                ConflictInfo(
                                    conflict_id=str(uuid.uuid4()),
                                    table=table,
                                    row_id=row_id,
                                    column="*",
                                    conflict_type="UPDATE_DELETE",
                                    base_value=dict(base_row),
                                    replica_a_value=None,  # A deleted
                                    replica_b_value=dict(row_b),
                                    replica_a_id=replica_a_id,
                                    replica_b_id=replica_b_id,
                                    replica_a_ts=(
                                        ts_a_delete if ts_a_delete > 0.0
                                        else time.time()
                                    ),
                                    replica_b_ts=(
                                        ts_b_update if ts_b_update > 0.0
                                        else ts_b.get(ts_key_row, time.time())
                                    ),
                                    detected_at=now_iso,
                                    status="flagged",
                                    explanation=(
                                        f"Concurrent DELETE vs UPDATE: "
                                        f"Replica {replica_a_id} deleted row "
                                        f"(last op on A: {a_last_op}), "
                                        f"Replica {replica_b_id} modified row."
                                    ),
                                )
                            )
                        # else: B has base-equal value, A deleted → clean delete, no conflict.

                    # -----------------------------------------------------------
                    # Case 5: Row in base, missing in both A and B -> DELETE vs DELETE
                    # -----------------------------------------------------------
                    # Idempotent convergence — both agree the row is gone.  No conflict.

                # ---------------------------------------------------------------
                # Case 6: Secondary UNIQUE Constraint / Index Collisions
                # ---------------------------------------------------------------
                unique_cols = self._get_unique_columns(
                    conn_a if self._table_exists(conn_a, table) else base_conn, table
                )
                for u_col in unique_cols:
                    if u_col == pk_col:
                        continue
                    new_a = {r_id: rows_a[r_id] for r_id in rows_a if r_id not in base_rows}
                    new_b = {r_id: rows_b[r_id] for r_id in rows_b if r_id not in base_rows}

                    for id_a, data_a in new_a.items():
                        val_a = data_a.get(u_col)
                        if val_a is None:
                            continue
                        for id_b, data_b in new_b.items():
                            if id_a == id_b:
                                continue  # Already handled as PK collision
                            val_b = data_b.get(u_col)
                            if self._values_equal(val_a, val_b):
                                conflicts.append(
                                    ConflictInfo(
                                        conflict_id=str(uuid.uuid4()),
                                        table=table,
                                        row_id=f"{id_a} vs {id_b}",
                                        column=u_col,
                                        conflict_type="UNIQUE_COLLISION",
                                        base_value=None,
                                        replica_a_value=dict(data_a),
                                        replica_b_value=dict(data_b),
                                        replica_a_id=replica_a_id,
                                        replica_b_id=replica_b_id,
                                        replica_a_ts=ts_a.get((table, str(id_a), u_col), time.time()),
                                        replica_b_ts=ts_b.get((table, str(id_b), u_col), time.time()),
                                        detected_at=now_iso,
                                        status="flagged",
                                        explanation=(
                                            f"UNIQUE constraint collision on column '{u_col}': "
                                            f"both replicas inserted value {val_a!r} under "
                                            f"different PKs ({id_a} vs {id_b})."
                                        ),
                                    )
                                )

        return DetectResult(conflicts=conflicts, skipped_tables=skipped_tables)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _connect(db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _list_user_tables(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '_ss_%' "
            "ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _get_pk_column(conn: sqlite3.Connection, table: str) -> str | None:
        """
        Returns the name of the single-column primary key, or ``None``.

        For composite primary keys, SQLite PRAGMA assigns ``pk=1`` for the
        first PK column and ``pk=2, 3, ...`` for subsequent columns.  We
        collect ALL columns where ``pk > 0`` and return ``None`` (signalling
        "composite or absent PK") whenever more than one column is found.
        """
        try:
            pragma = conn.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
            # Collect every column that participates in the PK (pk > 0)
            pks = [row["name"] for row in pragma if row["pk"] > 0]
            return pks[0] if len(pks) == 1 else None
        except sqlite3.OperationalError:
            return None

    @staticmethod
    def _get_unique_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        """Returns list of column names with UNIQUE index or constraint."""
        unique_cols: set[str] = set()
        try:
            idx_list = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
            for idx in idx_list:
                if idx["unique"]:
                    idx_name = idx["name"]
                    idx_info = conn.execute(f'PRAGMA index_info("{idx_name}")').fetchall()
                    if len(idx_info) == 1:
                        unique_cols.add(idx_info[0]["name"])
        except sqlite3.OperationalError:
            pass
        return list(unique_cols)

    @staticmethod
    def _get_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
        try:
            pragma = conn.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
            return [row["name"] for row in pragma]
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _fetch_rows(
        conn: sqlite3.Connection,
        table: str,
        pk_col: str,
        columns: list[str],
    ) -> dict[Any, dict[str, Any]]:
        col_list = ", ".join(f'"{c}"' for c in columns)
        try:
            rows = conn.execute(
                f'SELECT {col_list} FROM "{table}"'
            ).fetchall()
            return {row[pk_col]: dict(row) for row in rows}
        except sqlite3.OperationalError:
            return {}

    @staticmethod
    def _fetch_row(
        conn: sqlite3.Connection,
        table: str,
        pk_col: str,
        row_id: Any,
        columns: list[str],
    ) -> dict[str, Any] | None:
        col_list = ", ".join(f'"{c}"' for c in columns)
        try:
            row = conn.execute(
                f'SELECT {col_list} FROM "{table}" WHERE "{pk_col}" = ?',
                (row_id,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError:
            return None

    @staticmethod
    def _build_ts_map(
        conn: sqlite3.Connection,
        replica_id: str,
    ) -> dict[tuple[str, str, str], float]:
        """
        Build a ``(table, row_id, column) -> timestamp`` lookup from the
        ``_ss_change_log`` table.

        Uses the **minimum** composite timestamp for each key so that
        write-back entries (which always carry strictly larger timestamps)
        do not contaminate future conflict detection decisions.
        """
        ts_map: dict[tuple[str, str, str], float] = {}
        try:
            rows = conn.execute(
                "SELECT table_name,row_id,column_name,ts_pt,ts_l FROM _ss_change_log WHERE replica_id=?",
                (replica_id,),
            ).fetchall()
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_compacted_receipts'").fetchone():
                rows.extend(conn.execute(
                    "SELECT table_name,row_id,column_name,ts_pt,ts_l "
                    "FROM _ss_compacted_receipts WHERE replica_id=?", (replica_id,),
                ).fetchall())
            for row in rows:
                key = (row["table_name"], row["row_id"], row["column_name"])
                ts = float(row["ts_pt"]) * 1e6 + float(row["ts_l"] or 0)
                if key not in ts_map or ts < ts_map[key]:
                    ts_map[key] = ts
        except sqlite3.OperationalError:
            pass
        return ts_map

    @staticmethod
    def _build_op_map(
        conn: sqlite3.Connection,
        replica_id: str,
    ) -> dict[tuple[str, str], str]:
        """
        Build a ``(table, row_id) -> latest op_type`` lookup from ``_ss_change_log``.
        """
        op_map: dict[tuple[str, str], str] = {}
        try:
            rows = conn.execute(
                "SELECT table_name,row_id,op_type,ts_pt,ts_l FROM _ss_change_log WHERE replica_id=?",
                (replica_id,),
            ).fetchall()
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_compacted_receipts'").fetchone():
                rows.extend(conn.execute(
                    "SELECT table_name,row_id,op_type,ts_pt,ts_l FROM _ss_compacted_receipts WHERE replica_id=?",
                    (replica_id,),
                ).fetchall())
            rows.sort(key=lambda row: (row[3], row[4]))
            for row in rows:
                key = (row["table_name"], row["row_id"])
                op_type = row["op_type"] if "op_type" in row.keys() else "UPDATE"
                op_map[key] = op_type
        except sqlite3.OperationalError:
            pass
        return op_map

    @staticmethod
    def _get_row_update_ts(
        ts_map: dict[tuple[str, str, str], float],
        table: str,
        row_id_str: str,
        non_pk_cols: list[str],
    ) -> float:
        """
        Return the earliest UPDATE-operation timestamp for a given row.

        UPDATE operations are logged with the **actual column name** (not ``"*"``),
        so looking up ``(table, row_id, "*")`` would miss them.  This helper
        scans all non-PK columns and returns the minimum recorded timestamp.

        Returns ``0.0`` if no UPDATE-type entry is found for this row.
        """
        best = 0.0
        for col in non_pk_cols:
            key = (table, row_id_str, col)
            if key in ts_map:
                ts = ts_map[key]
                if best == 0.0 or ts < best:
                    best = ts
        return best

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        """Loose equality that handles None and numeric type coercions from SQLite."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return str(a) == str(b)
