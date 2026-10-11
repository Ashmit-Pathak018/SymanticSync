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
    """Describes a single detected concurrent conflict on a column."""
    conflict_id: str                  # UUID4 string
    table: str
    row_id: Any                       # Primary key value
    column: str
    base_value: Any
    replica_a_value: Any
    replica_b_value: Any
    replica_a_id: str
    replica_b_id: str
    replica_a_ts: float               # HLC or wall-clock timestamp
    replica_b_ts: float
    detected_at: str                  # ISO-8601 UTC


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

            for table in self._list_user_tables(base_conn):
                pk_col = self._get_pk_column(base_conn, table)
                if pk_col is None:
                    # Tables without a clear single PK are skipped
                    continue

                columns = self._get_column_names(base_conn, table)
                non_pk_cols = [c for c in columns if c != pk_col]

                # Fetch all base rows as {pk_value: {col: value}}
                base_rows = self._fetch_rows(base_conn, table, pk_col, columns)

                for row_id, base_row in base_rows.items():
                    row_a = self._fetch_row(conn_a, table, pk_col, row_id, columns)
                    row_b = self._fetch_row(conn_b, table, pk_col, row_id, columns)

                    if row_a is None or row_b is None:
                        # Row missing in one replica — not a column-level conflict
                        continue

                    for col in non_pk_cols:
                        base_val = base_row.get(col)
                        val_a = row_a.get(col)
                        val_b = row_b.get(col)

                        a_changed = not self._values_equal(val_a, base_val)
                        b_changed = not self._values_equal(val_b, base_val)

                        if a_changed and b_changed and not self._values_equal(val_a, val_b):
                            # True concurrent conflict
                            ts_key = (table, str(row_id), col)
                            conflicts.append(
                                ConflictInfo(
                                    conflict_id=str(uuid.uuid4()),
                                    table=table,
                                    row_id=row_id,
                                    column=col,
                                    base_value=base_val,
                                    replica_a_value=val_a,
                                    replica_b_value=val_b,
                                    replica_a_id=replica_a_id,
                                    replica_b_id=replica_b_id,
                                    replica_a_ts=ts_a.get(ts_key, time.time()),
                                    replica_b_ts=ts_b.get(ts_key, time.time()),
                                    detected_at=now_iso,
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
    def _list_user_tables(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name != '_ss_change_log' "
            "ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _get_pk_column(conn: sqlite3.Connection, table: str) -> str | None:
        """Returns the name of the single-column primary key, or None."""
        pragma = conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
        pks = [row["name"] for row in pragma if row["pk"] == 1]
        return pks[0] if len(pks) == 1 else None

    @staticmethod
    def _get_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
        pragma = conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
        return [row["name"] for row in pragma]

    @staticmethod
    def _fetch_rows(
        conn: sqlite3.Connection,
        table: str,
        pk_col: str,
        columns: list[str],
    ) -> dict[Any, dict[str, Any]]:
        col_list = ", ".join(f'"{c}"' for c in columns)
        rows = conn.execute(
            f'SELECT {col_list} FROM "{table}"'
        ).fetchall()
        return {row[pk_col]: dict(row) for row in rows}

    @staticmethod
    def _fetch_row(
        conn: sqlite3.Connection,
        table: str,
        pk_col: str,
        row_id: Any,
        columns: list[str],
    ) -> dict[str, Any] | None:
        col_list = ", ".join(f'"{c}"' for c in columns)
        row = conn.execute(
            f'SELECT {col_list} FROM "{table}" WHERE "{pk_col}" = ?',
            (row_id,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _build_ts_map(
        conn: sqlite3.Connection,
        replica_id: str,
    ) -> dict[tuple[str, str, str], float]:
        """
        Build a ``(table, row_id, column) -> timestamp`` lookup from the
        ``_ss_change_log`` table.  Returns an empty dict if the table does
        not exist.
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
                # Keep the MINIMUM (earliest/original) composite timestamp per key.
                # Write-back entries logged during sync have higher timestamps than
                # the original mutation; retaining the minimum ensures that write-back
                # entries do not inflate the authoritative timestamp and corrupt LWW
                # decisions in subsequent pairwise syncs.
                ts = float(row["ts_pt"]) * 1e6 + float(row["ts_l"] or 0)
                if key not in ts_map or ts < ts_map[key]:
                    ts_map[key] = ts
        except sqlite3.OperationalError:
            # _ss_change_log table absent — caller will use fallback timestamp
            pass
        return ts_map

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        """Loose equality that handles None and numeric type coercions from SQLite."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # Compare as strings to avoid int/float mismatches (e.g. 1 vs 1.0)
        return str(a) == str(b)
