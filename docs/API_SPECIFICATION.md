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

**Response:** `200 OK` — list of conflict records

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
  "replica_b_id": "inventory_device_b"
}
```

**Response:** `200 OK`
```json
{
  "status": "completed",
  "total_conflicts": 3,
  "auto_resolved": 2,
  "flagged_for_review": 1,
  "applied_changes": [...],
  "flagged_conflicts": ["uuid4"],
  "duration_ms": 12.4
}
```

---

### `POST /api/v1/sync/generate-conflict`
Inject controlled divergence for testing.

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

---

## Benchmark Endpoints

### `POST /api/v1/benchmark/run`
Run empirical benchmark comparison.

**Request Body:**
```json
{ "workload": "inventory" }
```

Supported workloads: `"inventory"`, `"notes"`, `"health"`

**Response:** `200 OK`
```json
{
  "workload": "inventory",
  "baseline_scr": 33.3,
  "semantic_sync_scr": 100.0,
  "baseline_convergence_rate": 100.0,
  "semantic_sync_convergence_rate": 100.0,
  "resolution_overhead_ms": 0.05,
  "total_conflicts_evaluated": 3,
  "correct_semantic_outcomes": 3
}
```

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
