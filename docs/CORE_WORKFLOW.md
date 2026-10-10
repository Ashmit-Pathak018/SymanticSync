# SemanticSync — Core Workflow

**Version:** 1.0

---

## Overview

SemanticSync's core workflow covers five sequential phases that take a developer from registering a database through to fully synchronized, semantically correct replicas.

```
Phase 1: Register → Phase 2: Design → Phase 3: Diverge → Phase 4: Sync → Phase 5: Verify
```

---

## Phase 1: Register a Database Workspace

```
POST /api/v1/databases
Body: { "name": "Inventory App", "path": "/data/inventory.db" }
```

1. `routes_databases.py` receives the request.
2. `SchemaInspector` validates that the file is a readable SQLite database.
3. A unique `db_id` (UUID4) is assigned.
4. The entry is persisted in `AppState.databases`.
5. `GET /api/v1/databases/{db_id}/schema` returns all tables and columns with normalized types.

---

## Phase 2: Design Semantic Policies

```
PUT /api/v1/databases/{db_id}/policies
Body: {
  "assignments": [
    { "table": "products", "column": "quantity", "policy": "SUM" },
    { "table": "products", "column": "description", "policy": "APPEND" },
    { "table": "products", "column": "sku", "policy": "REJECT" }
  ]
}
```

For each assignment:
1. `PolicyValidator.validate(policy, normalized_type)` is called.
2. If any assignment is incompatible (e.g. `SUM` on `TEXT`), the entire batch is rejected with `HTTP 422` and a detailed error per column.
3. Valid assignments are saved to `AppState.policies` as `"db_id:table:column" → policy_name`.

> The developer can also use the **Schema + Policy Designer** view in SemanticSync Studio to assign and validate policies interactively with real-time validation badges.

---

## Phase 3: Create Replicas and Diverge

### Create Replicas
```
POST /api/v1/databases/{db_id}/replicas
Body: { "replica_id": "device_a" }
```

`CRDTSyncEngine.create_replica("device_a")`:
1. Copies the base `.db` file to `data/device_a.db`.
2. Creates the `_ss_change_log` metadata table in the replica.
3. Registers the replica in `AppState.replicas`.

### Generate Controlled Divergence (Test/Demo)
```
POST /api/v1/sync/generate-conflict
Body: {
  "db_id": "...",
  "replica_a_id": "device_a",
  "replica_b_id": "device_b",
  "table": "products",
  "row_id": 1,
  "column": "quantity",
  "value_a": 115,
  "value_b": 120
}
```

This applies `value_a` to `device_a.db` and `value_b` to `device_b.db` independently, simulating what would happen when two users edit the same record offline.

---

## Phase 4: Synchronize

```
POST /api/v1/sync/run
Body: {
  "db_id": "...",
  "replica_a_id": "device_a",
  "replica_b_id": "device_b"
}
```

`CRDTSyncEngine.sync_replicas()` pipeline:

```
Step 1: ConflictDetector.detect()
   → Three-way diff: base vs. replica_a vs. replica_b
   → Returns list[ConflictInfo] for concurrent divergences only

Step 2: For each ConflictInfo:
   a. Look up assigned policy from AppState
   b. PolicyValidator.validate(policy, column_type) → fail fast if invalid
   c. SemanticResolver.resolve(policy, base_val, val_a, val_b, timestamps, ids)
      → Returns ResolutionResult { status, resolved_value, explanation }

Step 3: Write-back
   - If status == "resolved":
       UPDATE both replica_a and replica_b with resolved_value
   - If status == "flagged" (REJECT):
       Store in MergeManager without mutating replicas

Step 4: Return SyncResult {
   total_conflicts, auto_resolved, flagged_for_review,
   applied_changes, flagged_conflicts, duration_ms
}
```

---

## Phase 5: Verify and Review

### Inspect Resolved State
```
POST /api/v1/query
Body: { "db_id": "...", "replica_id": "device_a", "sql": "SELECT * FROM products" }
```
Both replicas now return `quantity = 135` — converged and semantically correct.

### Review Flagged Conflicts
```
GET /api/v1/conflicts?status=flagged
```
Returns any `REJECT`-policy conflicts awaiting manual resolution.

### Manual Resolution
```
POST /api/v1/conflicts/resolve
Body: { "conflict_id": "...", "resolution_mode": "pick_a" }
```
Modes: `auto` (use policy), `pick_a`, `pick_b`, `custom`.

---

## Walkthrough: Full Demo Sequence

```
1. POST /api/v1/seed          { "workload": "all" }
   → Creates inventory, notes, health databases + 3 replicas each

2. GET  /api/v1/databases     → Confirm 3 workspaces registered

3. GET  /api/v1/databases/db_inventory/schema
   → View table columns + assigned policies

4. POST /api/v1/sync/generate-conflict
   → Inject quantity divergence on device_a vs device_b

5. POST /api/v1/sync/run
   → Resolve conflicts using SUM/APPEND/REJECT policies

6. GET  /api/v1/conflicts     → Inspect resolved + flagged

7. POST /api/v1/benchmark/run { "workload": "inventory" }
   → Compare Baseline SCR vs SemanticSync SCR
```
