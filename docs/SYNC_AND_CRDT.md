# SemanticSync — Synchronization Mechanics & Logical Clocks

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Synchronization Architecture

SemanticSync decouples event ordering and causality tracking from the semantic resolution of divergent values:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SYNCHRONIZATION PIPELINE                        │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 1: Causality & Event Ordering (HLC + _ss_change_log)             │
│   - Assigns monotonically increasing causal timestamps                 │
│   - Establishes partial and total orders across replica nodes          │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 2: 3-Way Differential Divergence (ConflictDetector)              │
│   - Compares ancestor snapshot with replica states                     │
│   - Identifies clean updates vs. concurrent conflicts                  │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 3: Semantic Policy Middleware (SemanticResolver)                 │
│   - Applies schema-declared policies to conflicting cells              │
│   - Preserves business intent (additive deltas, text preservation)     │
├────────────────────────────────────────────────────────────────────────┤
│ Layer 4: Transactional Write-Back (CRDTSyncEngine)                     │
│   - Updates local SQLite replicas using parameterized SQL              │
│   - Maintains audit logs and records flagged triage cases              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Hybrid Logical Clock (HLC) Semantics

Replicas use an HLC implementation based on Kulkarni et al. (2014):

$$\text{HLC} = \langle pt, l, \text{node\_id} \rangle$$

Where:
- $pt \in \mathbb{R}$: Physical time in wall-clock seconds.
- $l \in \mathbb{Z}_{\ge 0}$: Logical counter to order events occurring within the same physical tick.
- $\text{node\_id} \in \text{String}$: Globally unique node identifier (UUID).

### State Transition Rules

#### On Local Send / Write
```python
wall = time.time()
if wall > self.pt:
    self.pt = wall
    self.l = 0
else:
    self.l += 1
```

#### On Remote Message Receive $(\text{recv\_pt}, \text{recv\_l})$
```python
wall = time.time()
max_pt = max(self.pt, recv_pt, wall)

if max_pt == self.pt == recv_pt:
    self.l = max(self.l, recv_l) + 1
elif max_pt == self.pt:
    self.l += 1
elif max_pt == recv_pt:
    self.l = recv_l + 1
else:
    self.l = 0

self.pt = max_pt
```

### Ordering Predicate
Given two clocks $\tau_1 = \langle pt_1, l_1, \text{id}_1 \rangle$ and $\tau_2 = \langle pt_2, l_2, \text{id}_2 \rangle$:
$$\tau_1 < \tau_2 \iff (pt_1 < pt_2) \lor (pt_1 = pt_2 \land l_1 < l_2) \lor (pt_1 = pt_2 \land l_1 = l_2 \land \text{id}_1 < \text{id}_2)$$

This establishes a strict total order across all tracked operations.

---

## 3. Change Log Tracking (`_ss_change_log`)

Every tracked replica maintains a change log table:

```sql
CREATE TABLE IF NOT EXISTS _ss_change_log (
    id           TEXT PRIMARY KEY,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    column_name  TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    ts_pt        REAL NOT NULL,
    ts_l         INTEGER NOT NULL DEFAULT 0,
    replica_id   TEXT NOT NULL,
    applied_at   TEXT NOT NULL,
    op_type      TEXT NOT NULL DEFAULT 'UPDATE'
);
```

### Operation Semantics:
- **`INSERT`:** `old_value` is `NULL`, `new_value` records row data JSON.
- **`UPDATE`:** `old_value` and `new_value` record divergence.
- **`INCREMENT`:** `old_value` records the local pre-operation numeric value and `new_value` records a signed numeric delta. The stable operation identity is the receipt key; the receiver adds the delta once and accepts reordered increment siblings for the same cell. This operation is separate from an absolute `UPDATE`/`apply_change` assignment. Mixed concurrent increments and assignments are not treated as interchangeable and must reach conflict handling.
- **`DELETE`:** `new_value` is `NULL`, acts as an explicit persistent tombstone.

### Log Lifecycle & Pruning Constraints (Phase 6)
- **Acknowledgement evidence:** The API sync route persists exact origin IDs observed in each enrolled replica's durable change log, along with source ID/sequence and HLC. An absent vector is not an empty successful ACK; it blocks compaction.
- **Pruning eligibility:** A change **must never** be pruned simply because one replica has read it. Exact acknowledgement by every enrolled replica, matching payload identity, dependency closure, and a strict **Causal Stability Check** are necessary per-entry eligibility conditions:
  $$T_{\text{stable}} = \min_{r \in \text{Replicas}}\;\max_{op \in ACK(r)} HLC(op)$$
-  Only dependency-closed entries with exact IDs acknowledged by all enrolled replicas and $\text{HLC} < T_{\text{stable}}$ are eligible to leave `_ss_change_log`; these conditions alone do not authorize pruning. The production route additionally requires validated committed checkpoint, archive, membership, snapshot, live-tail, history, and durable ACK evidence. The low-level helper trusts the caller-supplied eligibility set and cutoff. The HLC cutoff alone is never proof of receipt. Each local transaction stores compact receipt/dependency/hash metadata atomically with deleting the hot-log row and writing its checkpoint marker.
- **Membership/recovery:** Stale or newly enrolled replicas with no ACK vector pin the horizon. A committed checkpoint can resume only while the complete registered replica-ID set exactly matches its manifest membership; an added or removed member blocks that checkpoint before ACK reconciliation or pruning. After prior compaction, the API creates a new replica from an enrolled replica's current materialized snapshot; direct engine callers must do the same. The shared ancestor DB is not rewritten, because it is still the baseline for three-way conflict detection. Full operation payloads are retained in the checkpoint archive; compact receipt metadata in each replica does not retain them. AppState and the shared mutation lock remain single-process local coordination.

---

## 4. Write-Back Causal Dominance

When `sync_replicas()` resolves a conflict and writes the merged value back to both replicas, the write-back must be stamped with a timestamp that **strictly dominates** both input timestamps. Otherwise, a subsequent pairwise sync could misidentify the write-back as an older mutation, reversing a correctly resolved conflict.

### Algorithm

Given the composite timestamps of the two input log entries:
$$\tau_A = pt_A \times 10^6 + l_A, \quad \tau_B = pt_B \times 10^6 + l_B$$

The write-back clock is computed as:
$$pt_{\text{wb}} = \max(pt_A, pt_B), \quad l_{\text{wb}} = \max(l_A, l_B) + 1$$

This ensures:
$$\tau_{\text{wb}} = pt_{\text{wb}} \times 10^6 + l_{\text{wb}} > \max(\tau_A, \tau_B)$$

The write-back is then logged into `_ss_change_log` for both replicas using the post-tick HLC value (not the raw pre-tick custom value).

### Write-Back Timestamp Isolation in Conflict Detection

A critical correctness property: when `_build_ts_map` in `ConflictDetector` reconstructs the authoritative timestamp for a `(table, row_id, column)` key, it must return the **earliest (original mutation) timestamp**, not the latest write-back timestamp.

If write-back timestamps were returned, subsequent pairwise syncs would falsely treat the write-back entry as the authoritative causal epoch, causing LWW to select the wrong winner. For example:

1. `sync(A, B)` → resolves in B's favor → write-back logged on B with $\tau_{\text{wb}} > \tau_A, \tau_B$.
2. `sync(B, C)` runs. Without isolation, `_build_ts_map` for B returns $\tau_{\text{wb}}$ (very high) instead of B's original $\tau_B$.
3. B appears newer than C's original mutation → LWW incorrectly picks B over C.

**Fix (implemented in `_build_ts_map`):** Keeps the **minimum** composite timestamp per `(table, row_id, column)` key, so write-back log entries do not contaminate subsequent sync decisions.

### Scalar HLC vs. Vector Clocks

The scalar HLC used by SemanticSync establishes a **total order** over observed events on a single replica. It does **not** track causal dependencies between arbitrary pairs of replicas (that requires a vector clock or causal history). Specifically:

- HLC ordering is sufficient for **LWW** (single register with timestamp total order).
- HLC ordering is **not** sufficient to prove general CRDT convergence for `SUM` or `AVG` across mesh topologies.
- Multi-hop causal dependencies (A mutates, B reads A's mutation, B mutates) are not captured — only A→B direct exchange is causal.

---

## 5. Convergence — Tested Schedules vs. General Proofs

### Pairwise Convergence (Implemented)
When two replicas $R_A$ and $R_B$ synchronize against a base snapshot:
1. `ConflictDetector` identifies cells where both diverged.
2. For symmetric policies (`SUM`, `MIN`, `MAX`, `APPEND`), the resolved value is identical regardless of argument order.
3. For `LWW`, the total order over HLC ensures identical winner selection.
4. The resolved value is written back to both replicas within a local SQLite transaction.
5. Replicas reach state equivalence: $S_A \equiv S_B$.

### 3-Replica LWW Convergence — Verified Schedule Only

The test `test_three_replica_pairwise_sync_convergence_with_lww` verifies the following specific schedule:

$$\text{sync}(A, B) \;\to\; \text{sync}(B, C) \;\to\; \text{sync}(A, C)$$

with 10 ms wall-clock gaps between each mutation (ensuring strict HLC ordering). The test **passes** with the write-back timestamp isolation fix applied.

> [!IMPORTANT]
> This is evidence for **one specific sync schedule** under strict timestamp ordering. It is **NOT** a general convergence proof for:
> - Arbitrary sync orderings (e.g., $C \leftrightarrow A$ before $B \leftrightarrow A$)
> - Non-LWW policies (SUM, AVG, APPEND) under 3-replica mesh topologies
> - Simultaneous concurrent mutations across all 3 replicas
> - More than 3 replicas

### N-Replica Topology (Phase 3 Specification)
In peer-to-peer or mesh networks with $N \ge 3$ replicas:
- **Lattice Policies (`MIN`, `MAX`, `LWW`):** Converge under arbitrary pairwise sync orderings because the operators are associative and idempotent.
- **Non-Idempotent Policies (`SUM`, `AVG`):** Standard 3-way pairwise diff without per-node delta vectors can lead to double-counting if an update is synced via multiple intermediate paths ($A \to B \to C$ and $A \to C$).
- **Requirement for Phase 3:** Validate $N \ge 3$ sync topologies, quantify order-dependence, and document exact topology assumptions.

