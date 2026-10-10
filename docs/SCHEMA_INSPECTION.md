# SemanticSync — Schema Inspection

**Version:** 1.0

---

## Overview

`SchemaInspector` (`backend/engine/schema_inspector.py`) is the entry point for understanding the structure of any SQLite database registered with SemanticSync. It reads schema metadata without modifying the database.

---

## How It Works

SQLite exposes schema information through `PRAGMA` commands and `sqlite_master`. `SchemaInspector` uses both:

### `PRAGMA table_info(table_name)`
Returns one row per column:

| cid | name | type | notnull | dflt_value | pk |
|-----|------|------|---------|------------|-----|
| 0 | id | INTEGER | 1 | NULL | 1 |
| 1 | quantity | INTEGER | 0 | 0 | 0 |
| 2 | sku | TEXT | 1 | NULL | 0 |

- `pk > 0` → column is part of the primary key
- `notnull == 1` → NOT NULL constraint
- `dflt_value` → default value expression or NULL

### `sqlite_master`
Used to enumerate all user tables:
```sql
SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
```
Excludes SQLite internal tables and SemanticSync's own `_ss_change_log`.

---

## `ColumnInfo` Dataclass

```python
@dataclass
class ColumnInfo:
    name: str               # Column name (e.g., "quantity")
    normalized_type: str    # One of: INTEGER, REAL, TEXT, BLOB, NUMERIC
    raw_type: str           # Original declared type (e.g., "VARCHAR(255)")
    is_pk: bool             # True if part of PRIMARY KEY
    notnull: bool           # True if NOT NULL constraint
    default_value: Any      # Default value or None
```

---

## SQLite Type Affinity Mapping

SQLite uses **Type Affinity** rather than strict type enforcement. `SchemaInspector.normalise_type()` maps all SQLite type declarations to 5 canonical normalized types:

| Normalized Type | SQLite Declared Types |
|---|---|
| `INTEGER` | `INT`, `INTEGER`, `TINYINT`, `SMALLINT`, `MEDIUMINT`, `BIGINT`, `INT2`, `INT8`, `BOOLEAN`, `BOOL`, `DATE`, `DATETIME` |
| `REAL` | `REAL`, `DOUBLE`, `DOUBLE PRECISION`, `FLOAT` |
| `TEXT` | `CHARACTER`, `VARCHAR`, `VARYING CHARACTER`, `NCHAR`, `NATIVE CHARACTER`, `NVARCHAR`, `TEXT`, `CLOB`, `CHAR` |
| `BLOB` | `BLOB`, `BINARY`, `VARBINARY`, *(empty type string)* |
| `NUMERIC` | `NUMERIC`, `DECIMAL`, `DECIMAL(10,5)` — anything with "DECIMAL" |

### Affinity Resolution Rules
The normalization logic follows SQLite's affinity rules in priority order:
1. If "INT" appears anywhere → `INTEGER`
2. If "CHAR", "CLOB", "TEXT" appears → `TEXT`
3. If "BLOB" appears or type is empty → `BLOB`
4. If "REAL", "FLOA", "DOUB" appears → `REAL`
5. Otherwise → `NUMERIC`

---

## API

```python
from backend.engine.schema_inspector import SchemaInspector

inspector = SchemaInspector("/path/to/database.db")

# Inspect all tables
result = inspector.inspect_database()
# → { "products": [...ColumnInfo...], "orders": [...] }

# Inspect single table
columns = inspector.inspect_table("products")
# → list[ColumnInfo]

# Alias (legacy)
columns = inspector.get_columns("products")

# List all table names
tables = inspector.list_tables()
# → ["products", "suppliers", ...]

# Alias
tables = inspector.get_tables()

# Type normalization
norm = inspector.normalise_type("VARCHAR(255)")
# → "TEXT"
norm = inspector.normalize_type("BIGINT")
# → "INTEGER"
```

---

## Error Handling

| Condition | Exception |
|---|---|
| DB file not found | `FileNotFoundError("Database not found at: /path/to/db")` |
| File not a valid SQLite DB | `sqlite3.DatabaseError` propagates |
| Table doesn't exist | Returns empty `[]` (no exception) |

---

## Relationship to Policy Assignment

`SchemaInspector` provides the `normalized_type` that `PolicyValidator` uses to check compatibility:

```
SchemaInspector.inspect_table("products")
  → ColumnInfo { name="quantity", normalized_type="INTEGER" }

PolicyValidator.validate("SUM", "INTEGER")
  → ValidationResult { valid=True }
```

The schema schema is also surfaced in `GET /api/v1/databases/{db_id}/schema` where each column includes its currently assigned `policy` field.
