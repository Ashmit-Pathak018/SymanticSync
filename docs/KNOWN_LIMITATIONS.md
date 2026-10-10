# SemanticSync — Known Limitations

**Version:** 1.0

---

## Engine Limitations

### 1. Single-Column Primary Key Only
The conflict detector identifies rows using a single primary key column. Tables with composite primary keys (multi-column PKs) are not supported:

```sql
-- ✅ Supported
CREATE TABLE products (id INTEGER PRIMARY KEY, ...);

-- ❌ Not supported
CREATE TABLE order_items (order_id INTEGER, product_id INTEGER, PRIMARY KEY (order_id, product_id));
```

**Workaround:** Add a surrogate single-column PK (`rowid` or UUID) to composite-key tables.

---

### 2. No INSERT Conflict Handling
SemanticSync detects and resolves **UPDATE divergences** only. If two replicas independently INSERT rows with the same primary key value, this is not detected as a conflict — it is simply a write collision at the SQLite level.

**Workaround:** Use globally unique IDs (UUID4) for primary keys so concurrent inserts never collide.

---

### 3. No DELETE Handling
If Replica A deletes a row while Replica B updates it (or vice versa), the behavior is undefined. SemanticSync does not detect delete-update conflicts.

---

### 4. No Binary/BLOB Policy Support
The `APPEND` policy only works with `TEXT` columns. There is no supported policy for `BLOB` columns beyond `LWW` or `REJECT`. Binary diff/merge is not implemented.

---

### 5. No Multi-Replica Simultaneous Sync
The sync pipeline (`CRDTSyncEngine.sync_replicas()`) operates pairwise: Replica A vs. Replica B. For 3+ replicas, multiple pairwise sync runs are required. There is no N-way merge in v1.

---

### 6. SUM Policy Assumes Additive Independence
The `SUM` formula `(value_a + value_b - base_value)` is correct only when both replicas have made independent, additive changes relative to the same base. If both replicas set the field to an absolute value (not delta-based), SUM will produce incorrect results.

**Example where SUM is wrong:**
```
base=100, replica_a SET quantity=50 (reduce by 50), replica_b SET quantity=80 (reduce by 20)
SUM: 50 + 80 - 100 = 30  ← Incorrect (both intended to SET, not ADD)
```

The developer is responsible for understanding when SUM semantics apply.

---

### 7. No Schema Migration Support
SemanticSync reads schemas at startup via `PRAGMA`. If a schema is altered (columns added/removed) after policies are assigned, the policy assignments are stale. No automatic migration or re-validation is performed.

---

## API Limitations

### 8. In-Memory State Resets on Restart
`AppState` is backed by `data/registry.json`. If the file is deleted or corrupted, all registered databases, replicas, and policy assignments are lost. SQLite replica files are not affected (only the metadata registry).

---

### 9. No Concurrent Write Safety
`AppState.save()` uses `write_text()` which is not safe for concurrent multi-process access. Two simultaneous API requests that both call `save()` may race. This is acceptable for single-developer v1 use.

---

## Frontend Limitations

### 10. No Offline Support
The Studio frontend requires a running backend (`python main.py`). There is no frontend-only mode or cached data view.

---

## Research Limitations

### 11. Workload Diversity
The three benchmark workloads (Inventory, Notes, Healthcare) are constructed scenarios with 3 conflicts each. They are illustrative, not exhaustive. Evaluation on real-world SQLite applications has not been performed.

### 12. Baseline Comparison
The baseline is a simplified LWW simulation (the replica with the later timestamp wins). A production LWW CRDT implementation (e.g., Automerge's LWW register) might perform differently on edge cases.
