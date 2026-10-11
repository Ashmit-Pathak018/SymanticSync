# SemanticSync — Known Limitations & System Boundaries

**Version:** 2.0 (Reconciled)  
**Status:** Verification Baseline

---

## 1. Engine Boundaries & Current Scope (Phase 1 Baseline)

### 1. Single-Column Primary Key Requirement
- The current `ConflictDetector` identifies records via a single primary key column detected via `PRAGMA table_info`.
- Tables with composite primary keys (multi-column PKs) are skipped during conflict discovery.
- **Remediation Plan:** Phase 2 extension will support tuple-based row addressing `tuple(pk_cols)`.

### 2. Update Divergence Focus
- The current implementation detects conflicts when both replicas perform divergent `UPDATE` operations on an existing row ($S_A[k][c] \neq S_{\text{base}}[k][c] \land S_B[k][c] \neq S_{\text{base}}[k][c]$).
- Missing rows (resulting from un-synchronized `INSERT` or `DELETE`) are intentionally skipped by the current detector loop (`conflict_detector.py` lines 120–122).
- **Remediation Plan:** Full row-mutation handling (`INSERT vs INSERT`, `UPDATE vs DELETE`, `DELETE vs DELETE`) is specified in `CONFLICT_MODEL.md` for Phase 2.

### 3. Additive Delta Independence Assumption
- The `SUM` operator formula ($V_{\text{base}} + \Delta_A + \Delta_B$) assumes both replicas performed independent delta modifications relative to the ancestor base snapshot.
- If both replicas performed absolute assignments (e.g. `SET balance = 50` rather than `SET balance = balance - 50`), additive reconciliation is semantically invalid.
- Furthermore, unbounded subtractions risk underflow; this motivates the `BOUNDED_SUM` specification in Phase 3.

### 4. Non-Associativity of `AVG`
- Arithmetic mean is commutative ($A \sqcup B = B \sqcup A$) but strictly **non-associative**:
  $$\text{avg}(\text{avg}(A, B), C) \neq \text{avg}(A, \text{avg}(B, C))$$
- `AVG` is valid only for pairwise reconciliations where both values represent simultaneous sensor observations. It cannot serve as an arbitrary multi-replica mesh CRDT operator without state tuples $\langle \text{sum}, \text{count} \rangle$.

### 5. Pairwise Synchronization Model
- `CRDTSyncEngine.sync_replicas()` currently synchronizes two replicas ($R_A \leftrightarrow R_B$) against a shared base snapshot.
- Mesh topologies ($N \ge 3$) currently require sequential pairwise sync steps. Order-dependent convergence under non-idempotent operators is addressed in Phase 3.

---

## 2. Relational & Operational Limitations

### 6. Foreign Key Constraints
- SQLite foreign key checks (`PRAGMA foreign_keys = ON`) are not currently enforced during the write-back phase of `crdt_sync.py`.
- Deleting a parent row on one replica while mutating a child row on another will cause referential integrity anomalies.
- **Remediation Plan:** Phase 5 introduces the `_ss_quarantine` table protocol to isolate orphaned records.

### 7. Monotonic Change Log Accumulation
- The `_ss_change_log` table currently logs every tracked write without automated garbage collection.
- **Remediation Plan:** Phase 6 introduces causal stability checkpointing based on minimum acknowledged replica timestamps.

### 8. Single-Process Local Storage
- `AppState` persists metadata in `data/registry.json`. File updates use atomic text writes suitable for single-user local development. Multi-process concurrent server access is not supported.

### 9. Write-Back Timestamp Isolation (Addressed — Implementation Verified)
- When `sync_replicas()` resolves a conflict, it writes a new log entry to `_ss_change_log` on both replicas with a timestamp that strictly dominates both input timestamps. Without isolation, this write-back entry would be returned by `_build_ts_map` in subsequent syncs, causing LWW to incorrectly treat the write-back as the authoritative mutation timestamp.
- **Fix applied:** `_build_ts_map` now retains the **minimum** composite timestamp per `(table, row_id, column)` key, ensuring write-back entries do not contaminate future conflict detection decisions.
- **Residual risk:** This isolation strategy is correct only as long as write-backs are always stamped with timestamps strictly greater than any prior original mutation for that key. The invariant is maintained by the write-back algorithm (`pt_wb = max(pt_A, pt_B)`, `l_wb = max(l_A, l_B) + 1`). Verified by `test_hlc_write_back_causal_dominance`.

### 10. 3-Replica Convergence — Schedule-Specific Evidence, Not General Proof
- `test_three_replica_pairwise_sync_convergence_with_lww` verifies convergence for the specific sequence:
  $$\text{sync}(A, B) \;\to\; \text{sync}(B, C) \;\to\; \text{sync}(A, C)$$
  with 10 ms temporal gaps between each mutation (ensuring strict HLC ordering).
- This **does not** prove convergence for:
  - Alternative sync orderings (e.g., sync starting from C or reversing the sequence).
  - Non-LWW policies (SUM, AVG, APPEND) under 3-replica mesh topologies.
  - Simultaneous concurrent mutations on all 3 replicas at the same physical time.
  - $N > 3$ replicas.
- **Planned:** Phase 3 will formally specify and test N-replica convergence with varied sync orders, duplicate delivery, and offline partition scenarios.

