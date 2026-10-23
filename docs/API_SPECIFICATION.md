# SemanticSync — API Specification

**Version:** 1.0  
**Base URL:** `http://127.0.0.1:8000`  
**OpenAPI Docs:** `http://127.0.0.1:8000/docs`

All endpoints live under the `/api/v1` prefix.

---

## Authentication

None in v1 (local-only development server).

---

## Standard Error Responses

| Status | Meaning |
|---|---|
| `400 Bad Request` | Malformed request body or SQL error |
| `404 Not Found` | Database, replica, or conflict ID not found |
| `409 Conflict` | Cannot auto-resolve; requires manual review |
| `422 Unprocessable Entity` | Policy/type incompatibility |
| `500 Internal Server Error` | Unexpected server error |

---

## Database Endpoints

### `GET /api/v1/databases`
List all registered database workspaces.

**Response:** `200 OK`
```json
[
  {
    "id": "db_inventory",
    "name": "Inventory Workspace",
    "path": "data/inventory/inventory.db",
    "description": "...",
    "table_count": 1,
    "created_at": "2026-10-10T12:00:00Z"
  }
]
```

---

### `POST /api/v1/databases`
Register a new SQLite database.

**Request Body:**
```json
{
  "name": "My Database",
  "path": "/path/to/database.db",
  "description": "Optional description"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid4",
  "name": "My Database",
  "path": "/path/to/database.db",
  "description": "",
  "table_count": 3,
  "created_at": "2026-10-10T12:00:00Z"
}
```

---

### `GET /api/v1/databases/{db_id}`
Retrieve a registered database by ID.

**Response:** `200 OK` — DatabaseInfo object  
**Error:** `404` if not found

---

### `GET /api/v1/databases/{db_id}/schema`
Introspect the full schema with assigned policies.

**Response:** `200 OK`
```json
{
  "db_id": "db_inventory",
  "tables": [
    {
      "table_name": "products",
      "columns": [
        {
          "name": "quantity",
          "raw_type": "INTEGER",
          "normalized_type": "INTEGER",
          "is_pk": false,
          "notnull": true,
          "default_value": "0",
          "policy": "SUM"
        }
      ]
    }
  ]
}
```

---

### `POST /api/v1/databases/{db_id}/replicas`
Fork the base database into a new replica.

**Request Body:**
```json
{ "replica_id": "device_a" }
```

**Response:** `200 OK`
```json
{
  "replica_id": "device_a",
  "db_path": "data/device_a.db",
  "parent_db_id": "db_inventory",
  "created_at": "..."
}
```

---

### `GET /api/v1/databases/{db_id}/replicas`
List all replicas for a database.

---

## Policy Endpoints

### `GET /api/v1/databases/{db_id}/policies`
Return all policy assignments for a database.

**Response:** `200 OK`
```json
[
  {
    "table": "products",
    "column": "quantity",
    "normalized_type": "INTEGER",
    "policy": "SUM"
  }
]
```

---

### `PUT /api/v1/databases/{db_id}/policies`
Batch assign semantic policies.

For bounded signed-delta reconciliation, use the numeric policy string
`BOUNDED_SUM[min=<number>,max=<number>]`, for example
`BOUNDED_SUM[min=0,max=100]`. Bounds must be finite and inclusive. The UI does
not yet expose separate bound inputs.

**Request Body:**
```json
{
  "assignments": [
    { "table": "products", "column": "quantity", "policy": "SUM" },
    { "table": "products", "column": "description", "policy": "APPEND" }
  ]
}
```

**Response:** `200 OK` — list of `ValidationResult`  
**Error:** `422` if any assignment is invalid

---

### `POST /api/v1/validate-policy`
Validate a policy against a column's type (no side effects).

**Request Body:**
```json
{
  "table": "products",
  "column": "quantity",
  "policy": "SUM",
  "normalized_type": "INTEGER"
}
```

**Response:** `200 OK`
```json
{
  "valid": true,
  "policy": "SUM",
  "error_code": null,
  "error_message": null
}
```

---

### `GET /api/v1/policies/registry`
Return full registry of all policies with descriptions and compatible types.

---

## Conflict Endpoints

### `POST /api/v1/conflicts/detect`
Detect all concurrent divergences between two replicas.

**Request Body:**
```json
{
  "db_id": "db_inventory",
  "replica_a_id": "inventory_device_a",
  "replica_b_id": "inventory_device_b"
}
```

**Response:** `200 OK` — list of conflict records:
```json
[
  {
    "conflict_id": "uuid4",
    "db_id": "db_inventory",
    "table": "products",
    "row_id": 1,
    "column": "quantity",
    "conflict_type": "UPDATE_UPDATE",
    "base_value": 100,
    "value_a": 115,
    "value_b": 120,
    "replica_a_id": "inventory_device_a",
    "replica_b_id": "inventory_device_b",
    "status": "pending"
  }
]
```

The `X-SemanticSync-Skipped-Tables` response header contains comma-separated table names that could not be analyzed because they lack a supported single-column primary key.

---

### `POST /api/v1/conflicts/resolve`
Resolve a conflict by ID.

**Request Body:**
```json
{
  "conflict_id": "uuid4",
  "resolution_mode": "auto",
  "custom_value": null
}
```

`resolution_mode`: `"auto"` | `"pick_a"` | `"pick_b"` | `"custom"`

**Response:** `200 OK`
```json
{
  "status": "resolved",
  "result": 135,
  "policy": "SUM",
  "explanation": "SUM additive merge: base=100, delta_a=+15, delta_b=+20 => 135"
}
```

---

### `GET /api/v1/conflicts`
List conflicts.

**Query Params:**
- `status`: `all` | `pending` | `resolved` | `flagged`
- `db_id`: filter by database

---

### `GET /api/v1/conflicts/{conflict_id}`
Get a single conflict record.

---

## Sync Endpoints

### `GET /api/v1/sync/status`
Current sync overview.

**Response:** `200 OK`
```json
{
  "status": "ready",
  "registered_databases": 3,
  "registered_replicas": 9,
  "total_conflicts": 5,
  "pending_conflicts": 2,
  "flagged_conflicts": 1,
  "resolved_conflicts": 2
}
```

---

### `POST /api/v1/sync/run`
Execute the full synchronization pipeline.

**Request Body:**
```json
{
  "db_id": "db_inventory",
  "replica_a_id": "inventory_device_a",
  "replica_b_id": "inventory_device_b",
  "tombstone_policy": "FLAG_FOR_REVIEW"
}
```

`tombstone_policy` (optional): `"FLAG_FOR_REVIEW"` (default) | `"DELETE_WINS"` | `"UPDATE_RESURRECTS"`

**Response:** `200 OK`
```json
{
  "status": "completed",
  "total_conflicts": 3,
  "auto_resolved": 2,
  "flagged_for_review": 1,
  "applied_changes": [...],
  "flagged_conflicts": ["uuid4"],
  "duration_ms": 12.4,
  "skipped_tables": ["legacy_composite_table"]
}
```

`skipped_tables` lists unsupported tables. The SyncHub UI displays this list as a warning.

`rejected_operations` lists operations held because dependencies or expected row state did not validate. A sync can also raise after earlier operations committed; retry deduplicates those receipts by stable operation ID.

### `POST /api/v1/sync/compact`

Request: `{"db_id":"<registered database id>"}`. Compaction returns `status: retained` with zero pruned rows when any enrolled replica lacks a persisted ACK vector. Otherwise it reports the strict stable horizon, enrolled replicas, per-replica prune/retained counts, and aggregate row count. ACKs are exact operation IDs observed in durable replica logs; HLC is only a strict cutoff. Post-compaction replica creation bootstraps from an enrolled materialized replica, not the shared ancestor. This endpoint does not promise byte-level storage reduction or arbitrary offline-history recovery.

---

### `POST /api/v1/sync/generate-conflict`
Inject controlled divergence for testing.

### `POST /api/v1/sync/increment`
Apply one additive operation to a registered replica.

**Request Body:**
```json
{
  "db_id": "db_inventory",
  "replica_id": "inventory_device_a",
  "table": "products",
  "row_id": 1,
  "column": "quantity",
  "delta": 5
}
```

The endpoint returns `status`, a stable `operation_id`, the target replica ID,
and the persisted value. This is an operation-based increment and is distinct
from the existing absolute-value write used by `generate-conflict` and
`apply_change`. Increment deltas are deduplicated by operation identity and
can be applied in either order when the receiver has no concurrent non-increment
operation on that cell. A concurrent absolute edit is rejected for policy-level
conflict handling; the increment endpoint does not imply general N-way
convergence or bounded-counter allocation.

---

## Query Endpoint

### `POST /api/v1/query`
Execute SQL against base or replica.

**Request Body:**
```json
{
  "db_id": "db_inventory",
  "replica_id": null,
  "sql": "SELECT id, quantity FROM products"
}
```

**Response:** `200 OK`
```json
{
  "columns": ["id", "quantity"],
  "rows": [[1, 135], [2, 50]],
  "row_count": 2,
  "duration_ms": 0.8
}
```

Every SQL-console connection enables SQLite foreign-key enforcement before the statement runs. Base-database writes require `allow_write: true`; replica writes are allowed. These direct SQL writes are not captured in `_ss_change_log`, do not invoke orphan quarantine, and bypass the shared process mutation lock. FK constraints and schema-declared `ON DELETE` / `ON UPDATE` actions still apply. Use tracked mutation and sync APIs when operation replay or quarantine preservation is required.

---

## Quarantine Endpoints

### `GET /api/v1/quarantine`
Lists quarantined dependent-row payloads, optionally filtered by `db_id`, `table`, or `status`.

### `GET /api/v1/quarantine/{quarantine_id}`
Returns one quarantine record.

### `POST /api/v1/quarantine/{quarantine_id}/resolve`
Accepts `{"action":"confirmed_deleted"}` or `{"action":"relinked","new_parent_row_id":<parent-pk>}`. Relinking restores the quarantined row transactionally and validates its FK. Current relinking supports one single-column FK to a parent with a single-column primary key; unsupported FK shapes are rejected and remain quarantined.

---

## Benchmark Endpoints

### `POST /api/v1/benchmark/run`
Return the status of the development-only domain runner. This endpoint no longer runs a comparative experiment or returns numeric results.

**Request Body:**
```json
{ "workload": "inventory" }
```

Supported workloads: `"inventory"`, `"notes"`, `"health"`

**Response:** `200 OK`
```json
{
  "workload": "inventory",
  "evaluation_status": "illustrative_unvalidated",
  "explanation": "This development runner does not execute replica synchronization or a validated comparative experiment. Its former replica-B LWW proxy and hard-coded convergence values are unavailable. Domain-runner outputs are excluded from empirical results; use the separately documented stress benchmark for its limited, measured telemetry.",
  "baseline_scr": null,
  "semantic_sync_scr": null,
  "baseline_convergence_rate": null,
  "semantic_sync_convergence_rate": null,
  "resolution_overhead_ms": null,
  "total_conflicts_evaluated": null,
  "correct_semantic_outcomes": null
}
```

The endpoint response is explicitly `illustrative_unvalidated`; all former numeric fields are null and must not be interpreted as measurements. Historical cached values without this status are not displayed by the frontend. The domain-runner outputs are excluded from empirical results because the former implementation used a replica-B LWW proxy and direct resolver calls rather than replica synchronization. This does not affect the separate stress endpoint or its saved artifacts.

---

### `POST /api/v1/benchmark/stress`
Runs seeded real-replica stress trials (`num_operations`: 1000, 5000, or 10000; `conflict_density`: 0, 0.05, 0.20, or 0.50; `seed`; `trials`: 2–10, default 2; optional artifact export). Each paired trial runs both systems on the same generated trace and equivalent fresh data; execution order alternates. Writes are sequential followed by batch sync, not concurrent-writer trials.

Repeated-trial responses include per-metric sample count, median, minimum, maximum, and units in `summary_statistics`. The legacy `resolution_overhead_ms` field is the median paired SemanticSync batch-sync time minus LWW batch-sync time; it is not resolver-only time. API output does not include raw per-operation observations; request artifact export for JSON/CSV outputs.

Stress `baseline_scr` and `semantic_sync_scr` are null when there are no conflict rows. Otherwise SCR scores both replicas' final values for conflict rows only. The `*_row_value_agreement_rate` fields compare only ordered `bench_rows.value` observations, not full database state. Stress VRA is null because this workload defines no domain range or relational-integrity constraints. The legacy `resolution_overhead_ms` field is SemanticSync batch-sync time minus LWW batch-sync time; it is not resolver-only time.

---

### `GET /api/v1/metrics`
Return latest benchmark metrics.

---

## Seed Endpoint

### `POST /api/v1/seed`
Seed demo workloads.

**Request Body:**
```json
{ "workload": "all" }
```

Values: `"inventory"`, `"notes"`, `"health"`, `"all"`
