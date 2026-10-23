# SemanticSync — SQL Console Specification

**Version:** 1.0

---

## Overview

The **SQL Console** in SemanticSync Studio is an interactive query interface that lets developers run SQL directly against the base database or any registered replica. It is the primary tool for inspecting the effects of conflict resolution.

**Route:** `/workspace/:dbId/sql`

---

## Feature Set

| Feature | Description |
|---|---|
| **Target Selector** | Choose base DB or any replica to query against |
| **SQL Editor** | Syntax-highlighted, multi-line editor with keyboard shortcuts |
| **Execute** | Run the query with Ctrl+Enter or the Run button |
| **Results Table** | Paginated, sortable columns with type-aware formatting |
| **Query History** | Last 20 queries stored in `localStorage` |
| **Format SQL** | Basic SQL formatting (uppercase keywords, newlines) |

---

## UI Layout

```
┌──────────────────────────────────────────────────────────────┐
│  SQL Console — Inventory Workspace                            │
│  ────────────────────────────────────────────────────────────│
│  Target: [Base Database ▼]                                    │
│  ── or ──                                                     │
│  Target: [device_a ▼]  [device_b ▼]  [device_c ▼]            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  SELECT id, sku, quantity, description                  │ │
│  │  FROM products                                          │ │
│  │  WHERE quantity > 50                                    │ │
│  │                                                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│  [▶ Run (Ctrl+Enter)]  [Format SQL]  [Clear]                  │
│                                                               │
│  Results — 3 rows  (0.8ms)                                    │
│  ────────────────────────────────────────────────────────────│
│  id  │  sku       │  quantity  │  description               │
│  ────  ──────────   ──────────   ─────────────────────────  │
│  1   │  SKU-001   │  135       │  Widget A...               │
│  2   │  SKU-002   │  80        │  Widget B...               │
│  3   │  SKU-003   │  200       │  Widget C...               │
└──────────────────────────────────────────────────────────────┘
```

---

## API Backend

SQL execution is handled by:

```
POST /api/v1/query
Body: {
  "db_id": "db_inventory",
  "replica_id": "inventory_device_a",  // null for base
  "sql": "SELECT * FROM products"
}

Response: {
  "columns": ["id", "sku", "quantity", "description"],
  "rows": [[1, "SKU-001", 135, "Widget A..."]],
  "row_count": 1,
  "duration_ms": 0.8
}
```

---

## Safety Rules

The SQL Console enforces these rules on the backend (`routes_query.py`):

### Base Database
- Read-only by default: SQLite `query_only` mode rejects mutation statements unless `allow_write: true` is supplied.
- When opted in, a single SQLite statement is executed. The API rejects attempts to change `PRAGMA foreign_keys`.

### Replicas
- Writes are allowed through the console. Each connection starts with SQLite foreign-key enforcement enabled.

### Replication and Quarantine Boundary
- SQL-console writes are direct SQLite writes: they do not create operation IDs or change-log entries, do not invoke dependent-row quarantine, and bypass the shared process mutation lock.
- Foreign-key constraints still reject invalid writes, and schema-declared `ON DELETE` / `ON UPDATE` actions still apply. A declared cascade may remove dependent rows without creating quarantine records.
- Use tracked engine APIs for mutations that must be replayed or quarantined. External processes can bypass both the process lock and per-connection foreign-key setting.

---

## Editor Features

### Keyboard Shortcuts
| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Execute query |
| `Ctrl+Shift+F` | Format SQL |
| `Ctrl+L` | Clear editor |
| `↑` in empty editor | Load previous query from history |

### Syntax Highlighting (CodeMirror 6)
- SQLite dialect keywords highlighted: `SELECT`, `FROM`, `WHERE`, `JOIN`, `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`
- Table and column names: no highlighting (dynamic)
- String literals: string color
- Numeric literals: numeric color

---

## Results Table

- Null values displayed as `NULL` in muted text
- Integer values: right-aligned, monospace
- Float values: right-aligned, 4 decimal places by default
- Text values: left-aligned, truncated at 80 chars with tooltip on hover
- Boolean/bit: `true` / `false`

---

## Comparison Mode

A special sub-mode allowing side-by-side comparison:

```
[device_a] │ [device_b]

id  │ qty   │   id  │ qty
────  ─────    ────  ─────
1   │ 115   │   1   │ 135   ← differs! (orange highlight)
2   │ 80    │   2   │ 80    ← same (no highlight)
```

Triggered by selecting two replicas simultaneously. Differences highlighted in `warning` color.
