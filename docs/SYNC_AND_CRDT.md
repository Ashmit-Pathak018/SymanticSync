# SemanticSync — CRDT Synchronization and Hybrid Logical Clocks

**Version:** 1.0

---

## 1. The Two-Layer Model

SemanticSync uses a **two-layer** approach to synchronization:

```
Layer 1: CRDT Convergence (CRDTSyncEngine)
   → Ensures all replicas agree on A common state
   → Mechanism: Hybrid Logical Clock (HLC) + change log exchange

Layer 2: Semantic Resolution (SemanticResolver)
   → Ensures that common state is CORRECT according to domain meaning
   → Mechanism: Policy-driven deterministic resolution functions
```

Generic CRDT frameworks provide Layer 1 but not Layer 2. SemanticSync adds Layer 2.

---

## 2. Hybrid Logical Clock (HLC)

SemanticSync uses HLC (Kulkarni et al., 2014) for ordering events across replicas.

### HLC Structure
```python
@dataclass
class HLC:
    pt: float   # Physical timestamp (wall-clock seconds)
    l: int      # Logical counter (incremented on ties)
    node_id: str  # Unique replica identifier
```

### HLC Properties
- Always advances monotonically, even when wall clocks are identical
- Preserves causality: if event A caused event B, `hlc(A) < hlc(B)`
- Deterministic tie-breaking via `node_id` lexicographic comparison

### HLC Tick Algorithm
```
On SEND:
    pt = max(self.pt, physical_time())
    if pt == self.pt: l += 1
    else: l = 0
    self.pt = pt

On RECEIVE(recv_pt, recv_l):
    pt = max(self.pt, recv_pt, physical_time())
    if pt == self.pt == recv_pt: l = max(self.l, recv_l) + 1
    elif pt == self.pt: l += 1
    elif pt == recv_pt: l = recv_l + 1
    else: l = 0
```

---

## 3. Change Log (`_ss_change_log`)

Every replica maintains a `_ss_change_log` table created by `CRDTSyncEngine.create_replica()`:

```sql
CREATE TABLE IF NOT EXISTS _ss_change_log (
    id           TEXT PRIMARY KEY,    -- UUID4 change identifier
    table_name   TEXT NOT NULL,       -- Target table
    row_id       TEXT NOT NULL,       -- Row primary key value
    column_name  TEXT NOT NULL,       -- Column modified
    old_value    TEXT,                -- Value before this change
    new_value    TEXT,                -- Value after this change
    ts_pt        REAL NOT NULL,       -- HLC physical timestamp
    ts_l         INTEGER NOT NULL,    -- HLC logical counter
    replica_id   TEXT NOT NULL,       -- Which replica made the change
    applied_at   TEXT NOT NULL        -- ISO-8601 UTC wall timestamp
);
```

Every tracked write via `CRDTSyncEngine.apply_change()` inserts a row into this log.

---

## 4. Replica Management

### Creating a Replica
```python
engine = CRDTSyncEngine(base_db_path="data/inventory.db", data_dir="data")
replica_path = engine.create_replica("device_a")
```

Steps:
1. `shutil.copy2(base_db_path, "data/device_a.db")` — fork the base
2. Execute `CREATE TABLE IF NOT EXISTS _ss_change_log ...` in the copy
3. Initialize a `HLC` clock for `device_a`
4. Return the path to the new replica

### Applying a Tracked Change
```python
engine.apply_change(
    replica_db_path="data/device_a.db",
    replica_id="device_a",
    table="products",
    row_id=1,
    column="quantity",
    new_value=115
)
```

Steps:
1. Read current (old) value from replica
2. Execute parameterized `UPDATE` on the replica
3. Tick the HLC clock for this replica
4. Insert a row into `_ss_change_log`
5. Return the change_id

---

## 5. Full Sync Pipeline

`CRDTSyncEngine.sync_replicas()` orchestrates the complete synchronization:

```
sync_replicas(
    replica_a_path, replica_b_path, base_path,
    replica_a_id, replica_b_id,
    policies: { table: { column: policy_name } }
)
```

### Algorithm

```
1. ConflictDetector.detect(a, b, base, id_a, id_b)
   → conflicts: list[ConflictInfo]

2. For each conflict in conflicts:
   a. Get HLC timestamps from _ss_change_log for this cell
   b. Look up policy from `policies` dict; default "REJECT"
   c. Get normalized column type via SchemaInspector
   d. PolicyValidator.validate(policy, col_type)
      → If invalid: treat as REJECT
   e. SemanticResolver.resolve(
          policy, base_val, val_a, val_b,
          ts_a, ts_b, id_a, id_b
      )
      → ResolutionResult { status, resolved_value }

3. If status == "resolved":
   → _write_resolved(replica_a_path, ..., resolved_value)
   → _write_resolved(replica_b_path, ..., resolved_value)
   → auto_resolved += 1

4. If status == "flagged":
   → MergeManager.add_conflict(conflict)
   → MergeManager.apply_resolution(conflict_id, resolution)
   → flagged_conflicts.append(conflict_id)

5. Return SyncResult {
   total_conflicts, auto_resolved, flagged_for_review,
   applied_changes, flagged_conflicts, duration_ms
}
```

---

## 6. Convergence Guarantee

Given the same base state and the same two replica states:
- **All symmetric policies** (SUM, AVG, MIN, MAX, APPEND, REJECT) produce **identical results** regardless of which replica is passed as `a` vs `b`
- **LWW** produces identical results due to deterministic timestamp + replica_id ordering
- **Both replicas are updated with the same resolved value** in a single sync run

Therefore, after `sync_replicas()`, `replica_a[table][row][col] == replica_b[table][row][col]` for all auto-resolved conflicts.

---

## 7. Delta Sync

`get_changes_since(replica_path, since_ts)` returns all `_ss_change_log` entries with `(ts_pt * 1e6 + ts_l) > since_ts`. This enables incremental sync in future versions — only exchange changes made after the last sync checkpoint.
