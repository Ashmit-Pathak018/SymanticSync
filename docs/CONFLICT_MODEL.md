# SemanticSync — Conflict Taxonomy & Resolution Model

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Relational Mutation Conflict Taxonomy

In distributed relational replicas, conflicts can manifest across multiple structural dimensions. SemanticSync structures conflicts into a formal matrix:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   RELATIONAL CONFLICT TAXONOMY                         │
├─────────────────────┬──────────────────────────┬───────────────────────┤
│ Mutation Pair       │ Conflict Character       │ Resolution Strategy   │
├─────────────────────┼──────────────────────────┼───────────────────────┤
│ UPDATE vs UPDATE    │ Cell-level divergence    │ Semantic Policy Merge │
│ INSERT vs INSERT    │ Primary Key collision    │ Rekey / LWW / Triage  │
│ INSERT vs INSERT    │ UNIQUE index collision   │ Flag for Review       │
│ UPDATE vs DELETE    │ Ghost Row modification   │ Tombstone Policy      │
│ DELETE vs DELETE    │ Concurrent deletion      │ Idempotent converge   │
│ Parent DEL vs Child │ Foreign Key orphan       │ Quarantine Table      │
└─────────────────────┴──────────────────────────┴───────────────────────┘
```

---

## 2. Implemented Model: UPDATE vs UPDATE Divergence

### Detection Algorithm (Three-Way Diff)
Let $S_{\text{base}}, S_A, S_B$ be snapshots of a relational table across the base ancestor and two replicas.

For each row identified by primary key value $k$:
1. If row $k$ exists in $S_{\text{base}}, S_A, S_B$:
   - For each non-PK column $c$:
     $$a\_changed = (S_A[k][c] \neq S_{\text{base}}[k][c])$$
     $$b\_changed = (S_B[k][c] \neq S_{\text{base}}[k][c])$$
     $$\text{diverged} = (S_A[k][c] \neq S_B[k][c])$$
2. If $a\_changed \land b\_changed \land \text{diverged}$:
   - Emit `ConflictInfo` record representing a true concurrent conflict.
3. Clean Update Handling:
   - If only $a\_changed$ is true, replica B adopts $S_A[k][c]$ cleanly (no conflict).
   - If only $b\_changed$ is true, replica A adopts $S_B[k][c]$ cleanly (no conflict).
   - If neither or identical, state is already converged.

---

## 3. Specification for Phased Extensions

### 3.1 INSERT vs INSERT Collisions (Phase 2)
When both replicas independently insert a row with the same primary key:
- **Scenario A (UUID / Natural Key Collision):**
  - If payload differs: Compare HLC timestamps. If `LWW` is configured, later insert wins. If invariant policies are present, mark row as `flagged` in `MergeManager`.
  - Automatic rekeying is permitted **only** when the table uses an auto-incrementing surrogate PK and has no external foreign key dependencies pointing to the local uncommitted key.
- **Scenario B (Secondary UNIQUE Constraint Violation):**
  - Replicas insert distinct PKs, but identical values on a column with a `UNIQUE` constraint.
  - Safe default: Move one insertion to a staging/flagged queue; never silently overwrite unique constraints.

### 3.2 UPDATE vs DELETE & Tombstone Semantics (Phase 2)
When Replica A updates row $k$ while Replica B deletes row $k$:
- **Tombstone Model:** Deletions are recorded in `_ss_change_log` with `new_value = NULL` and metadata `op_type = 'DELETE'`.
- **Configurable Tombstone Policies:**
  - `DELETE_WINS` (Default for general entities): The deletion takes precedence; the row remains deleted, and the update is archived in the conflict audit log.
  - `UPDATE_RESURRECTS`: If the update carries an HLC timestamp strictly greater than the deletion, the row is re-inserted with the updated fields.
  - `FLAG_FOR_REVIEW`: When the table contains critical data, generate an explicit conflict record for manual intervention.

### 3.3 DELETE vs DELETE (Phase 2)
- Replicas concurrently delete the same row $k$.
- **Semantics:** Idempotent no-op. Both agree that row $k$ does not exist. No conflict generated.

### 3.4 Foreign Key & Parent-Child Invariants (Phase 5)
When Replica A deletes parent record `orders[id=10]` while Replica B inserts or updates child record `order_items[id=99, order_id=10]`:
- **Orphan Quarantine Protocol:**
  1. The synchronization engine detects that applying child update/insert violates SQLite `PRAGMA foreign_keys = ON`.
  2. The orphan child row is routed into a dedicated `_ss_quarantine` table along with its payload and target foreign key reference.
  3. A high-priority conflict is registered in `MergeManager` with category `FOREIGN_KEY_ORPHAN`.
  4. The base database remains referentially intact (no broken FK pointers).

---

## 4. Conflict Lifecycle & Persistence

```
                    ┌────────────────────────┐
                    │    Divergence Event    │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   ConflictDetector     │
                    └───────────┬────────────┘
                                │
                 ┌──────────────┴──────────────┐
                 ▼                             ▼
       [Automated Resolution]        [Safety Guard / REJECT]
                 │                             │
                 ▼                             ▼
       ┌──────────────────┐          ┌───────────────────┐
       │ Status: resolved │          │  Status: flagged  │
       │ Apply Write-Back │          │ Store in Manager  │
       └──────────────────┘          └─────────┬─────────┘
                                               │
                                               ▼
                                     ┌───────────────────┐
                                     │   Manual Triage   │
                                     │ pick_a / b / custom│
                                     └─────────┬─────────┘
                                               │
                                               ▼
                                     ┌───────────────────┐
                                     │ Status: resolved  │
                                     │ Apply Write-Back  │
                                     └───────────────────┘
```

### Durability
Every conflict record contains:
- `conflict_id`: Unique UUID4
- `table`, `row_id`, `column`
- Ancestor base value, Replica A value, Replica B value
- Originating replica IDs and HLC timestamps
- Current resolution status (`pending`, `resolved`, `flagged`)
- Audit rationale explaining the mathematical or policy decision
