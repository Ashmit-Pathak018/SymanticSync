"""
test_schema.py
==============
Pytest tests for :class:`~backend.engine.schema_inspector.SchemaInspector`.

Coverage
--------
* Introspect a known schema and verify column names, types, and PK detection.
* Verify that all common SQLite type variants normalise correctly.
* FileNotFoundError is raised for a non-existent database path.
* Inspect a table with no rows still returns full schema metadata.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.engine.schema_inspector import SchemaInspector, normalize_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db(path: Path, ddl: str, rows: list[tuple] | None = None, insert: str = "") -> Path:
    """Create a SQLite DB at *path* with the given DDL and optional rows."""
    conn = sqlite3.connect(str(path))
    conn.execute(ddl)
    if rows and insert:
        conn.executemany(insert, rows)
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# Tests: basic introspection
# ---------------------------------------------------------------------------


def test_inspect_known_schema_columns(tmp_path: Path) -> None:
    """Inspector returns correct column names for a known schema."""
    db = make_db(
        tmp_path / "test.db",
        "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL, qty INTEGER, price REAL);",
    )
    inspector = SchemaInspector(db)
    columns = inspector.get_columns("items")
    col_names = [c["name"] for c in columns]
    assert col_names == ["id", "name", "qty", "price"]


def test_inspect_primary_key_detected(tmp_path: Path) -> None:
    """Inspector correctly marks the primary key column."""
    db = make_db(
        tmp_path / "test.db",
        "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);",
    )
    inspector = SchemaInspector(db)
    columns = {c["name"]: c for c in inspector.get_columns("items")}
    assert columns["id"]["is_pk"] is True
    assert columns["name"]["is_pk"] is False


def test_inspect_normalized_types(tmp_path: Path) -> None:
    """Inspector maps declared types to correct canonical types."""
    db = make_db(
        tmp_path / "test.db",
        "CREATE TABLE t (a INTEGER, b TEXT, c REAL, d BLOB, e NUMERIC);",
    )
    inspector = SchemaInspector(db)
    columns = {c["name"]: c for c in inspector.get_columns("t")}
    assert columns["a"]["normalized_type"] == "INTEGER"
    assert columns["b"]["normalized_type"] == "TEXT"
    assert columns["c"]["normalized_type"] == "REAL"
    assert columns["d"]["normalized_type"] == "BLOB"
    assert columns["e"]["normalized_type"] == "NUMERIC"


def test_inspect_declared_type_preserved(tmp_path: Path) -> None:
    """Inspector preserves the raw declared type alongside the normalized one."""
    db = make_db(
        tmp_path / "test.db",
        "CREATE TABLE t (val VARCHAR(255));",
    )
    inspector = SchemaInspector(db)
    columns = inspector.get_columns("t")
    assert columns[0]["declared_type"] == "VARCHAR(255)"
    assert columns[0]["normalized_type"] == "TEXT"


def test_get_tables_returns_all_tables(tmp_path: Path) -> None:
    """get_tables() returns all user-defined tables."""
    db_path = tmp_path / "multi.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE alpha (id INTEGER PRIMARY KEY);")
    conn.execute("CREATE TABLE beta  (id INTEGER PRIMARY KEY);")
    conn.commit()
    conn.close()

    inspector = SchemaInspector(db_path)
    tables = inspector.get_tables()
    assert set(tables) == {"alpha", "beta"}


def test_inspect_returns_full_dict(tmp_path: Path) -> None:
    """inspect() returns a dict keyed by table name."""
    db_path = tmp_path / "full.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);")
    conn.commit()
    conn.close()

    inspector = SchemaInspector(db_path)
    schema = inspector.inspect()
    assert "users" in schema
    assert len(schema["users"]) == 2


# ---------------------------------------------------------------------------
# Tests: type normalisation coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declared, expected",
    [
        ("INTEGER",          "INTEGER"),
        ("INT",              "INTEGER"),
        ("TINYINT",          "INTEGER"),
        ("SMALLINT",         "INTEGER"),
        ("BIGINT",           "INTEGER"),
        ("BOOLEAN",          "INTEGER"),
        ("REAL",             "REAL"),
        ("FLOAT",            "REAL"),
        ("DOUBLE",           "REAL"),
        ("DOUBLE PRECISION", "REAL"),
        ("TEXT",             "TEXT"),
        ("VARCHAR(100)",     "TEXT"),
        ("NVARCHAR(50)",     "TEXT"),
        ("CHARACTER(10)",    "TEXT"),
        ("CLOB",             "TEXT"),
        ("BLOB",             "BLOB"),
        ("NONE",             "BLOB"),
        ("NUMERIC",          "NUMERIC"),
        ("DECIMAL(10,2)",    "NUMERIC"),
        ("DATE",             "TEXT"),
        ("DATETIME",         "TEXT"),
        ("TIMESTAMP",        "TEXT"),
        ("",                 "BLOB"),   # empty → fallback BLOB
    ],
)
def test_normalize_type_coverage(declared: str, expected: str) -> None:
    """normalize_type() maps all common SQLite type variants correctly."""
    assert normalize_type(declared) == expected


# ---------------------------------------------------------------------------
# Tests: error conditions
# ---------------------------------------------------------------------------


def test_file_not_found_raises(tmp_path: Path) -> None:
    """SchemaInspector raises FileNotFoundError for non-existent DB path."""
    with pytest.raises(FileNotFoundError):
        SchemaInspector(tmp_path / "does_not_exist.db")


def test_empty_table_still_returns_schema(tmp_path: Path) -> None:
    """Inspecting a table with no rows still returns full column metadata."""
    db = make_db(
        tmp_path / "empty.db",
        "CREATE TABLE empty_tbl (id INTEGER PRIMARY KEY, value TEXT);",
    )
    inspector = SchemaInspector(db)
    columns = inspector.get_columns("empty_tbl")
    # Schema should still be returned even with zero rows
    assert len(columns) == 2
    assert columns[0]["name"] == "id"
    assert columns[1]["name"] == "value"


def test_notnull_flag_detected(tmp_path: Path) -> None:
    """Inspector correctly reports NOT NULL constraints."""
    db = make_db(
        tmp_path / "nn.db",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, required TEXT NOT NULL, optional TEXT);",
    )
    inspector = SchemaInspector(db)
    columns = {c["name"]: c for c in inspector.get_columns("t")}
    assert columns["required"]["notnull"] is True
    assert columns["optional"]["notnull"] is False
