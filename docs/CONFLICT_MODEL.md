# SemanticSync — Conflict Taxonomy & Row-Mutation Resolution Model

**Version:** 3.0 (Phase 2 Implemented Specification)  
**Status:** Implementation-Ready Specification

---

## 1. Relational Mutation Conflict Taxonomy

In distributed relational replicas, mutations are not limited to cell-level divergence between existing rows. Mutations include full row lifecycles: `INSERT`, `UPDATE`, and `DELETE`.

SemanticSync defines a formal 2-dimensional conflict matrix across these mutations:

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           RELATIONAL MUTATION CONFLICT MATRIX                         │
├─────────────────────┬──────────────────────────┬──────────────────────────────────────┤
│ Mutation Pair       │ Conflict Character       │ Default Resolution & Policy          │
├─────────────────────┼──────────────────────────┼──────────────────────────────────────┤
│ UPDATE vs UPDATE    │ Cell-level divergence    │ Semantic Policy Merge (SUM, LWW...)  │
│ INSERT vs INSERT    │ Primary Key collision    │ Idempotent if equal; else Flag/Review│
│ INSERT vs INSERT    │ UNIQUE index collision   │ Flag for Review (Never overwrite)    │
│ UPDATE vs DELETE    │ Ghost Row mutation       │ Causal: Del wins; Conc: Flag/Review  │
│ DELETE vs DELETE    │ Concurrent deletion      │ Idempotent convergence (No conflict) │
│ DELETE vs UPDATE    │ Symmetric ghost row      │ Symmetric to UPDATE vs DELETE        │
│ Parent DEL vs Child │ Foreign Key orphan       │ Quarantine Table (Phase 5)           │
└─────────────────────┴──────────────────────────┴──────────────────────────────────────┘
```

---

## 2. Operation Identity & Metadata Contract

Every row mutation in SemanticSync generates an immutable operation record in `_ss_change_log`:

```sql
CREATE TABLE IF NOT EXISTS _ss_change_log (
    id           TEXT PRIMARY KEY,        -- UUID4 operation identity
    table_name   TEXT NOT NULL,           -- Target table
    row_id       TEXT NOT NULL,           -- Row primary key identity
    column_name  TEXT NOT NULL,           -- Target column, or '*' for row-level ops
    old_value    TEXT,                    -- Pre-mutation value or serialized JSON
    new_value    TEXT,                    -- Post-mutation value or serialized JSON (NULL on DELETE)
    ts_pt        REAL NOT NULL,           -- Hybrid Logical Clock physical time
    ts_l         INTEGER NOT NULL,        -- Hybrid Logical Clock logical counter
    replica_id   TEXT NOT NULL,           -- Originating replica node ID
    applied_at   TEXT NOT NULL,           -- ISO-8601 UTC timestamp
    op_type      TEXT NOT NULL DEFAULT 'UPDATE' -- 'INSERT' | 'UPDATE' | 'DELETE'
);
```

### Operation Identity Invariants:
1. **Uniqueness:** Each operation has a distinct UUID `id`.
2. **Causal Monotonicity:** Within a replica, `(ts_pt * 1e6 + ts_l)` is strictly monotonically increasing.
3. **Row Identity:** Rows are identified by their primary key `row_id`.
4. **Operation Type (`op_type`):**
   - `INSERT`: Created new row. `old_value` is `NULL`. `new_value` holds full row JSON or column value.
   - `UPDATE`: Modified existing cell or row. `old_value` and `new_value` record divergence.
   - `DELETE`: Deleted row. `new_value` is `NULL`. Acts as an explicit durable tombstone.

---

## 3. Row Mutation Conflict Resolution Rules

### 3.1 INSERT vs INSERT Collisions

When row $k$ does not exist in the ancestor base database $S_{\text{base}}$, but exists in both $S_A$ and $S_B$:

1. **Identical Duplicate Delivery (Idempotency):**
   - If row payloads are identical ($S_A[k] \equiv S_B[k]$):
   - **Resolution:** No conflict. Both replicas inserted the identical logical entity. State converges seamlessly.
2. **Primary Key Collision (Divergent Payloads):**
   - If row payloads differ ($S_A[k] \neq S_B[k]$):
   - **Default Rule:** Flagged for manual review (`status = 'flagged'`, `conflict_type = 'INSERT_INSERT'`).
   - **Payload Preservation:** Both competing full row payloads are durably preserved in `ConflictInfo` (`replica_a_value` and `replica_b_value` contain full row dictionaries/JSON).
   - **Safety Directive:** Do not silently overwrite data. Automatic rekeying is prohibited unless explicit schema rules and foreign-key preservation contracts exist.
3. **Secondary UNIQUE Index Collisions:**
   - Both replicas insert rows with different PKs ($k_1 \neq k_2$), but sharing an identical value on a column governed by a `UNIQUE` constraint or unique index.
   - **Resolution:** Marked as `flagged` (`conflict_type = 'UNIQUE_CONSTRAINT_COLLISION'`). Rows remain in their respective replicas without cross-copying to avoid SQLite constraint violations.

---

## 3.2 UPDATE vs DELETE & Tombstone Semantics

When row $k$ existed in $S_{\text{base}}$, but has been deleted in one replica (e.g., $R_B$) while modified in the other ($R_A$):

1. **Causally Ordered (Update followed by Delete):**
   - If change logs show that deletion on $R_B$ causally happened **after** the update on $R_A$ (e.g. via HLC dominance or vector awareness):
   - **Resolution:** Deletion wins cleanly. The tombstone is propagated to $R_A$.
2. **Truly Concurrent UPDATE vs DELETE:**
   - If both operations were performed concurrently against the base snapshot without knowledge of each other:
   - **Default Policy (Safety First):** `FLAG_FOR_REVIEW`.
     - Record emitted with `conflict_type = 'UPDATE_DELETE'`.
     - `replica_a_value`: The updated row snapshot or cell change.
     - `replica_b_value`: `None` (representing deletion/tombstone).
     - State is not silently resurrected or permanently lost until explicit resolution or policy execution.
   - **Configurable `tombstone_policy`:**
     - `DELETE_WINS`: Tombstone wins, row deleted on both replicas, update preserved in conflict audit log.
     - `UPDATE_RESURRECTS`: The update wins, row re-inserted or retained with updated values.
     - `FLAG_FOR_REVIEW` (Default): Manual triage required.

---

## 3.3 DELETE vs DELETE Idempotency

When row $k$ existed in $S_{\text{base}}$ and has been deleted in **both** $S_A$ and $S_B$:

- **Resolution:** Clean convergence (no conflict emitted).
- **Semantics:** Idempotent no-op.
- **Tombstone Propagation:** Both replicas agree that row $k$ does not exist. Tombstone log entries are retained in `_ss_change_log` for future replicas and causal stability checking.

---

## 4. Conflict Lifecycle, Auditability & Recovery

Every conflict detected by `ConflictDetector` is recorded in `MergeManager` with full structural metadata:

```python
@dataclass
class ConflictInfo:
    conflict_id: str             # UUID4 unique ID
    table: str                   # SQLite table name
    row_id: Any                  # Primary key value
    column: str                  # Column name, or '*' for row-level conflicts
    conflict_type: str           # 'UPDATE_UPDATE' | 'INSERT_INSERT' | 'UPDATE_DELETE' | 'UNIQUE_COLLISION'
    base_value: Any              # Common ancestor value or row dict (None for INSERTs)
    replica_a_value: Any         # Replica A value or row payload
    replica_b_value: Any         # Replica B value or row payload
    replica_a_id: str            # Replica A identifier
    replica_b_id: str            # Replica B identifier
    replica_a_ts: float          # Causal timestamp A
    replica_b_ts: float          # Causal timestamp B
    detected_at: str             # ISO-8601 UTC timestamp
    status: str = "pending"      # 'pending' | 'resolved' | 'flagged'
    resolution_mode: Optional[str] = None # 'auto' | 'pick_a' | 'pick_b' | 'custom'
    resolved_value: Optional[Any] = None
    explanation: Optional[str] = None
```

### Recovery & Idempotent Write-Back Contract
1. **Transactional Execution:** All write-backs execute inside an explicit `conn.transaction` block.
2. **Retry Safety:** Applying the same resolution multiple times is strictly idempotent.
3. **Full Audit Trail:** Resolved conflicts retain `resolved_value`, `resolved_at`, and `explanation` in `MergeManager` and `AppState`.
