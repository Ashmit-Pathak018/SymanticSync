"""
backend/engine/schema_inspector.py
────────────────────────────────────
Domain-agnostic SQLite schema introspection via standard PRAGMAs.

Responsibilities
----------------
* Enumerate all user tables in a .db file (excluding SQLite internals).
* Introspect columns: name, declared type, PK flag, NOT NULL, default.
* Normalise SQLite affinity types → canonical set (INTEGER, REAL, TEXT, BLOB, NUMERIC).
* Never reference domain concepts (products, patients, etc.).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


# Mapping of SQLite type affinity keywords → canonical type label.
_AFFINITY_RULES = [
    # INTEGER rules
    ("INT", "INTEGER"),
    ("BOOLEAN", "INTEGER"),
    # REAL rules
    ("DOUBLE", "REAL"),
    ("FLOAT", "REAL"),
    ("REAL", "REAL"),
    # NUMERIC rules
    ("DECIMAL", "NUMERIC"),
    ("NUMERIC", "NUMERIC"),
    # TEXT rules
    ("CHAR", "TEXT"),
    ("CLOB", "TEXT"),
    ("TEXT", "TEXT"),
    ("VARCHAR", "TEXT"),
    ("DATE", "TEXT"),
    ("TIME", "TEXT"),
    # BLOB rules
    ("BLOB", "BLOB"),
    ("NONE", "BLOB"),
]


def normalise_type(raw: str | None) -> str:
    """
    Map a raw SQLite declared type to one of: INTEGER, REAL, TEXT, BLOB, NUMERIC.
    """
    if raw is None or not raw.strip():
        return "BLOB"

    upper = raw.strip().upper()

    for keyword, canonical in _AFFINITY_RULES:
        if keyword in upper:
            return canonical

    return "BLOB"


# Alias for US English spelling
normalize_type = normalise_type


class SchemaInspector:
    """
    Introspects the schema of a SQLite database file.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._validate_path()

    def list_tables(self) -> list[str]:
        """Return names of all user-defined tables (excludes sqlite_*)."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_ss_%' ORDER BY name;"
            ).fetchall()
        return [r[0] for r in rows]

    def get_tables(self) -> list[str]:
        """Alias for list_tables()."""
        return self.list_tables()

    def inspect_table(self, table_name: str) -> list[dict[str, Any]]:
        """
        Return a list of column dicts for table_name.
        """
        with self._connect() as con:
            rows = con.execute(
                f"PRAGMA table_info({self._quote(table_name)});"
            ).fetchall()
        columns = []
        for row in rows:
            # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
            _, name, raw_type, notnull, default_value, pk = row
            raw_str = raw_type if raw_type is not None else ""
            norm_str = normalise_type(raw_str)
            columns.append(
                {
                    "name": name,
                    "raw_type": raw_str,
                    "declared_type": raw_str,
                    "normalized_type": norm_str,
                    "is_pk": bool(pk),
                    "notnull": bool(notnull),
                    "default_value": default_value,
                }
            )
        return columns

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        """Alias for inspect_table()."""
        return self.inspect_table(table_name)

    def inspect_all(self) -> dict[str, list[dict[str, Any]]]:
        """Return a mapping of table_name -> list[column_dict]."""
        return {t: self.inspect_table(t) for t in self.list_tables()}

    def inspect(self) -> dict[str, list[dict[str, Any]]]:
        """Alias for inspect_all()."""
        return self.inspect_all()

    def table_count(self) -> int:
        return len(self.list_tables())

    def is_valid(self) -> bool:
        try:
            self._validate_path()
            self.list_tables()
            return True
        except Exception:
            return False

    def _validate_path(self) -> None:
        path = Path(self.db_path)
        if not path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path!r}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {self.db_path!r}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
