# SemanticSync — Engineering Audit Report & Scope Reconciliations

**Date:** October 2026  
**Auditor:** SemanticSync AI Engineering Agent  
**Context:** Phase 0 Documentation Reconciliation & Project Direction Alignment

---

## 1. Verified Repository State vs. Unverified Claims

An empirical audit was executed across the existing repository files, git history, and automated test suite.

| Component / Claim | Documented Claim in v1.0 Docs | Verified Reality in Codebase | Audit Finding & Action Taken |
|---|---|---|---|
| **Automated Tests** | 56 passing tests | **56 passed in 0.84 seconds** on Python 3.14 via `pytest`. | ✅ **Verified Fact.** Accurately reported. |
| **Algebraic Semilattices** | "All policies form a join-semilattice with HLC" | Only `MIN`, `MAX`, and `LWW` are strictly join-semilattices. `AVG` is non-associative. `SUM` is non-idempotent. | ⚠️ **Corrected.** Reconciled in `POLICY_SPECIFICATION.md` with explicit algebraic boundaries. |
| **Row Mutation Conflicts** | "Complete conflict detection" | `ConflictDetector` currently evaluates only `UPDATE vs UPDATE` on rows sharing identical PKs. Rows missing in one replica are skipped (`line 120-122`). | ⚠️ **Clarified.** Reconciled as Phase 1 baseline; `INSERT/DELETE` handling scheduled for Phase 2. |
| **Multi-Replica Convergence**| "Arbitrary multi-replica mesh convergence" | Current test suite tests only 2-replica pairwise convergence (`test_sync.py`). | ⚠️ **Clarified.** Pairwise model documented; $N \ge 3$ mesh testing scheduled for Phase 3. |
| **Benchmark Scale** | Implied generalized benchmark performance | Benchmark suite currently measures 3 fixed scenarios across 3 workloads (9 total conflicts). | ⚠️ **Clarified.** Disclosed as Tier 1 unit verification. Tier 2 (1,000 conflicts) scheduled for Phase 4. |
| **Foreign Key Safety** | "Automatic parent resurrection" | SQLite `PRAGMA foreign_keys` is not checked during sync write-back. | ⚠️ **Corrected.** Rejected automatic parent resurrection; scheduled orphan quarantine for Phase 5. |
| **Literature References** | General citations | Unverified claims that no existing system addresses multi-table sync. | ⚠️ **Corrected.** Replaced with verified citations (Balegas, Gomes, Marr) in `LITERATURE_REVIEW.md`. |

---

## 2. List of Scope Reconciliations & Decisions

1. **Explicit Contribution Boundaries:**
   - Established that SemanticSync is a schema-driven semantic synchronization middleware for SQLite.
   - Removed any overreaching claims of inventing CRDTs, local-first computing, or general conflict resolution.
2. **Policy Algebraic Rigor:**
   - Formally documented why `AVG` cannot be an arbitrary N-way CRDT merge operator without state tuples $\langle \text{sum}, \text{count} \rangle$.
   - Explicitly documented double-counting risks in naive pairwise `SUM` delta reconciliation.
3. **Safety Defaults:**
   - Codified `REJECT` / `FLAG_FOR_REVIEW` as the required default whenever automated resolution is not provably safe.
   - Prohibited automatic parent resurrection for foreign key violations; established durable quarantine table design (`_ss_quarantine`).
4. **Transparent Benchmark Reporting:**
   - Clearly separated currently measured results (33.3% LWW vs 100.0% SemanticSync across 9 scenarios) from future targets (1,000–10,000 conflicts).
5. **No Implementation Code Modified in Phase 0:**
   - Strict adherence to Phase 0 constraints: only Markdown documentation was modified. Zero application code or database files were touched.

---

## 3. Phase 1 Follow-Up — Corrections Applied (October 2026)

Three technical corrections were required before Phase 2:

### 3.1 AVG Idempotency — Corrected

| Property | Before Correction | After Correction |
|---|---|---|
| Idempotent? | ❌ No | ✅ Yes (algebraically, avg(x,x)=x) |

**Explanation:** The algebraic identity $\text{avg}(x, x) = x$ holds for any scalar $x$. The prior classification incorrectly conflated sync-level state idempotency (which requires base snapshot refresh) with operation-level algebraic idempotency. The policy specification table and `POLICY_SPECIFICATION.md` §2.2 have been corrected accordingly.

Non-associativity remains the critical constraint: $\text{avg}(\text{avg}(a, b), c) \neq \text{avg}(a, \text{avg}(b, c))$, making AVG unsuitable for arbitrary N-replica mesh synchronization without $\langle \text{sum}, \text{count} \rangle$ state tuples.

### 3.2 HLC Write-Back Causal Dominance — Verified and Fixed

**Defect identified:** After `sync(A, B)` wrote back a resolution with $\tau_{\text{wb}}$ stamped on B's `_ss_change_log`, the subsequent `sync(B, C)` call saw B's write-back timestamp (very high) via `_build_ts_map`. This made B appear causally newer than C's original mutation, causing LWW to incorrectly pick B's value over C's.

**Fixes applied:**
1. **`crdt_sync.py` — Write-back HLC:** The composite write-back timestamp is now computed as $pt_{\text{wb}} = \max(pt_A, pt_B)$, $l_{\text{wb}} = \max(l_A, l_B) + 1$, ensuring strict dominance. Write-back is logged with the post-tick HLC value (not the raw pre-tick input).
2. **`conflict_detector.py` — `_build_ts_map`:** Changed from keeping the **last** composite timestamp per key to keeping the **minimum** (original mutation) timestamp per key. Write-back entries no longer contaminate LWW comparisons in future syncs.

**Verification:** `test_hlc_write_back_causal_dominance` and `test_three_replica_pairwise_sync_convergence_with_lww` both pass with the fix applied.

**Residual limitation documented:** Scalar HLC is sufficient for LWW total ordering but does not capture multi-hop causal dependencies between replicas (documented in `SYNC_AND_CRDT.md` §4 and `KNOWN_LIMITATIONS.md` §9).

### 3.3 Convergence Claims — Narrowed

The prior report stated 3-replica LWW convergence was verified. This is now precisely scoped:

- **Verified schedule:** `sync(A,B) → sync(B,C) → sync(A,C)` with 10 ms temporal gaps between mutations.
- **NOT a general proof:** Alternative orderings, non-LWW policies, simultaneous concurrent mutations, and $N > 3$ replicas remain unverified.
- Claims updated in `SYNC_AND_CRDT.md` §5 and `KNOWN_LIMITATIONS.md` §10.

### 3.4 APPEND Multi-Operation Coverage Added

New test `test_append_multi_operation_and_reordering` verifies:
- Multiple sequential local edits on a replica (only the last local value participates in sync, not every intermediate).
- Repeat sync on an already-converged APPEND column is idempotent (no duplicate concatenation).

### 3.5 Final Test Report

| Metric | Phase 1 Baseline | Phase 1 Follow-Up |
|---|---|---|
| Total tests | 79 | **82** |
| Passing | 79 | **82** |
| Failing | 0 | **0** |
| New correctness tests | — | 3 (REQ-AUD-08, 09, 10) |
| Command | `python -m pytest backend/tests/ -v` | Same |
| Python | 3.14.3 | 3.14.3 |
| Duration | ~1.6 s | ~1.7 s |

**Phase 1 follow-up is complete. Phase 2 approved and implemented.**

---

## 4. Phase 2 Audit Report — Full Row-Mutation Conflict Model (October 2026)

### 4.1 Implementation Scope Verified

Phase 2 extended SemanticSync from single-PK, cell-level UPDATE vs UPDATE to a complete row-mutation conflict model:

1. **INSERT vs. INSERT:**
   - **Primary Key Collision:** Independent insertions with divergent payloads are detected and flagged (`status = 'flagged'`, `conflict_type = 'INSERT_INSERT'`). Full row payloads from both replicas are preserved. No silent overwrites or auto-rekeying.
   - **Idempotent Delivery:** Identical row payloads delivered to both replicas converge with zero conflicts.
   - **Secondary UNIQUE Collisions:** Independent insertions with different PKs but colliding values on a column governed by a UNIQUE index/constraint are detected and flagged (`conflict_type = 'UNIQUE_COLLISION'`).
2. **UPDATE vs. DELETE & Tombstone Semantics:**
   - Deletions are logged with explicit `op_type = 'DELETE'` and recorded in `_ss_change_log`.
   - Concurrent UPDATE vs DELETE is flagged by default (`FLAG_FOR_REVIEW`) with both the updated row payload and tombstone preserved in `ConflictInfo`.
   - Configurable tombstone policies: `DELETE_WINS` (row deleted across replicas) and `UPDATE_RESURRECTS` (updated payload resurrected across replicas) implemented and verified.
3. **DELETE vs. DELETE:**
   - Concurrent deletions across 2 and 3 replicas converge idempotently with zero spurious conflicts.
4. **Delivery Idempotency & Conflict Recovery:**
   - Repeated synchronization after resolution does not re-apply or duplicate changes.
   - All conflicts are durably persisted in `MergeManager` with full structural evidence.

### 4.2 Test Metrics

| Metric | Phase 1 Baseline | Phase 1 Follow-Up | Phase 2 Complete |
|---|---|---|---|
| Total tests | 79 | 82 | **92** |
| Passing | 79 | 82 | **92** |
| Failing | 0 | 0 | **0** |
| New mutation tests | — | — | 10 (`test_mutation_conflicts.py`) |
| Duration | ~1.6 s | ~1.7 s | ~1.2 s |

### 4.3 Remaining Boundaries for Future Phases
- **BOUNDED_SUM & Invariant Policies:** Phase 3.
- **N-Replica Mesh Synchronization ($N \ge 3$ arbitrary topologies):** Phase 3.
- **Foreign-Key Orphan Quarantine Table (`_ss_quarantine`):** Phase 5.
- **Change Log Compaction & Causal Stability Pruning:** Phase 6.


