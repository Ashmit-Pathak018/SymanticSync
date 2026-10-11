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
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
    conflict_type: str = "UPDATE_UPDATE" # UPDATE_UPDATE, INSERT_INSERT, UPDATE_DELETE, UNIQUE_COLLISION
    status: str = "pending"           # pending, resolved, flagged
    resolution_mode: Any = None       # auto, pick_a, pick_b, custom
    resolved_value: Any = None
    explanation: Any = None


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
    ) -> list[ConflictInfo]:
        """
        Detect all concurrent conflicts between two replicas relative to base.

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
        list[ConflictInfo]
            All cells where both replicas diverged from the base value.
        """
        conflicts: list[ConflictInfo] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        with (
            self._connect(base_db) as base_conn,
            self._connect(replica_a_db) as conn_a,
            self._connect(replica_b_db) as conn_b,
        ):
            # Build timestamp lookup tables from change logs (if present)
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
                # Find pk column from whichever DB has the table
                pk_col = (
                    self._get_pk_column(base_conn, table)
                    or self._get_pk_column(conn_a, table)
                    or self._get_pk_column(conn_b, table)
                )
                if pk_col is None:
                    # Tables without a clear single PK are skipped
                    continue

                columns = (
                    self._get_column_names(base_conn, table)
                    or self._get_column_names(conn_a, table)
                    or self._get_column_names(conn_b, table)
                )
                non_pk_cols = [c for c in columns if c != pk_col]

                # Fetch all rows from all three sides
                base_rows = self._fetch_rows(base_conn, table, pk_col, columns) if self._table_exists(base_conn, table) else {}
                rows_a = self._fetch_rows(conn_a, table, pk_col, columns) if self._table_exists(conn_a, table) else {}
                rows_b = self._fetch_rows(conn_b, table, pk_col, columns) if self._table_exists(conn_b, table) else {}

                all_row_ids = set(base_rows.keys()) | set(rows_a.keys()) | set(rows_b.keys())

                for row_id in all_row_ids:
                    in_base = row_id in base_rows
                    in_a = row_id in rows_a
                    in_b = row_id in rows_b

                    base_row = base_rows.get(row_id)
                    row_a = rows_a.get(row_id)
                    row_b = rows_b.get(row_id)

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
                                        replica_a_ts=ts_a.get(ts_key, ts_a.get(ts_key_row, time.time())),
                                        replica_b_ts=ts_b.get(ts_key, ts_b.get(ts_key_row, time.time())),
                                        detected_at=now_iso,
                                        status="pending",
                                    )
                                )

                    # -----------------------------------------------------------
                    # Case 2: Row NOT in base, inserted in both A and B -> INSERT vs INSERT
                    # -----------------------------------------------------------
                    elif not in_base and in_a and in_b:
                        # Check if rows are identical (idempotent duplicate)
                        rows_identical = all(
                            self._values_equal(row_a.get(c), row_b.get(c)) for c in columns
                        )
                        if not rows_identical:
                            # Genuine PK collision with divergent payloads
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
                                    explanation=f"INSERT collision on PK {row_id!r} with divergent row payloads.",
                                )
                            )

                    # -----------------------------------------------------------
                    # Case 3: Row in base, present in A but missing in B -> UPDATE vs DELETE
                    # -----------------------------------------------------------
                    elif in_base and in_a and not in_b:
                        # B deleted row_id. Did A mutate it?
                        a_mutated = any(
                            not self._values_equal(row_a.get(c), base_row.get(c)) for c in non_pk_cols
                        )
                        if a_mutated:
                            # Concurrent UPDATE vs DELETE
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
                                    replica_a_ts=ts_a.get(ts_key_row, time.time()),
                                    replica_b_ts=ts_b.get(ts_key_row, time.time()),
                                    detected_at=now_iso,
                                    status="flagged",
                                    explanation=f"Concurrent UPDATE vs DELETE: Replica {replica_a_id} modified row, Replica {replica_b_id} deleted row.",
                                )
                            )

                    # -----------------------------------------------------------
                    # Case 4: Row in base, present in B but missing in A -> DELETE vs UPDATE
                    # -----------------------------------------------------------
                    elif in_base and not in_a and in_b:
                        # A deleted row_id. Did B mutate it?
                        b_mutated = any(
                            not self._values_equal(row_b.get(c), base_row.get(c)) for c in non_pk_cols
                        )
                        if b_mutated:
                            # Concurrent DELETE vs UPDATE
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
                                    replica_a_ts=ts_a.get(ts_key_row, time.time()),
                                    replica_b_ts=ts_b.get(ts_key_row, time.time()),
                                    detected_at=now_iso,
                                    status="flagged",
                                    explanation=f"Concurrent DELETE vs UPDATE: Replica {replica_a_id} deleted row, Replica {replica_b_id} modified row.",
                                )
                            )

                    # -----------------------------------------------------------
                    # Case 5: Row in base, missing in both A and B -> DELETE vs DELETE
                    # -----------------------------------------------------------
                    # Idempotent convergence! Both agree it is deleted. No conflict emitted.

                # ---------------------------------------------------------------
                # Case 6: Secondary UNIQUE Constraint / Index Collisions
                # ---------------------------------------------------------------
                unique_cols = self._get_unique_columns(conn_a if self._table_exists(conn_a, table) else base_conn, table)
                for u_col in unique_cols:
                    if u_col == pk_col:
                        continue
                    # Check across newly inserted rows (rows not in base)
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
                                # UNIQUE constraint collision!
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
                                        explanation=f"UNIQUE constraint collision on column '{u_col}': both replicas inserted value {val_a!r} under different PKs ({id_a} vs {id_b}).",
                                    )
                                )

        return conflicts

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
        """Returns the name of the single-column primary key, or None."""
        try:
            pragma = conn.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
            pks = [row["name"] for row in pragma if row["pk"] == 1]
            return pks[0] if len(pks) == 1 else None
        except sqlite3.OperationalError:
            return None

    @staticmethod
    def _get_unique_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        """Returns list of column names with UNIQUE index or constraint."""
        unique_cols: set[str] = set()
        try:
            # Check PRAGMA index_list
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
        """
        ts_map: dict[tuple[str, str, str], float] = {}
        try:
            rows = conn.execute(
                "SELECT table_name, row_id, column_name, ts_pt, ts_l "
                "FROM _ss_change_log WHERE replica_id = ?",
                (replica_id,),
            ).fetchall()
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
                "SELECT table_name, row_id, op_type, ts_pt, ts_l "
                "FROM _ss_change_log WHERE replica_id = ? "
                "ORDER BY ts_pt ASC, ts_l ASC",
                (replica_id,),
            ).fetchall()
            for row in rows:
                key = (row["table_name"], row["row_id"])
                # Latest row in time sets latest op_type
                op_type = row["op_type"] if "op_type" in row.keys() else "UPDATE"
                op_map[key] = op_type
        except sqlite3.OperationalError:
            pass
        return op_map

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        """Loose equality that handles None and numeric type coercions from SQLite."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # Compare as strings to avoid int/float mismatches (e.g. 1 vs 1.0)
        return str(a) == str(b)

