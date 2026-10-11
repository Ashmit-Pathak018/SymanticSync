# SemanticSync — Prioritized Phased Implementation Plan

**Version:** 2.0 (Reconciled)  
**Status:** Approved Roadmap & Engineering Contract

---

## Phased Delivery Overview

```
Phase 0: Documentation Reconciliation               ✅ COMPLETE (This Step)
Phase 1: Core Correctness & Auditing               📋 NEXT UP
Phase 2: Full Row-Mutation Conflict Model          📋 SPECIFIED
Phase 3: Bounded Operations & N-Replica Validation  📋 SPECIFIED
Phase 4: Reproducible Benchmark Stress Harness     📋 SPECIFIED
Phase 5: Relational Foreign Key Invariant Extension 📋 SPECIFIED
Phase 6: Operational Log Compaction & Checkpoint   📋 SPECIFIED
Phase 7: Studio Integration & Research Release     📋 SPECIFIED
```

---

## Detailed Phases, Tasks & Acceptance Criteria

### Phase 0: Documentation Reconciliation ✅
- **Objective:** Align all specifications, research documents, and roadmaps with verified reality and approved scope.
- **Constraints:** Modify Markdown documentation only. Zero changes to application implementation code.
- **Acceptance Criteria:**
  - All 31 Markdown files reconciled.
  - Clear separation between verified facts, working features, and planned extensions.
  - Requirement-to-test traceability matrix established.

---

### Phase 1: Core Correctness & Adversarial Auditing
- **Objective:** Audit existing engine behavior for causality, determinism, idempotency, and edge-case handling.
- **Dependencies:** Phase 0 approved.
- **Tasks:**
  1. Add property-based tests for commutativity across all policies: $f(A, B) \equiv f(B, A)$.
  2. Audit `SUM` behavior under negative numbers, zero, and missing ancestor values.
  3. Audit `APPEND` behavior under empty strings, unicode characters, and duplicate inputs.
  4. Audit `LWW` tie-breaking under identical physical and logical clock timestamps.
  5. Validate atomic write-backs within local SQLite transactions (`BEGIN IMMEDIATE`).
- **Acceptance Criteria:**
  - New dedicated test suite `test_adversarial_resolution.py` passing 100%.
  - Zero unhandled exceptions or state corruptions under invalid inputs.

---

### Phase 2: Full Row-Mutation Conflict Model
- **Objective:** Expand conflict detection and resolution beyond cell-level UPDATE divergences.
- **Dependencies:** Phase 1 complete.
- **Tasks:**
  1. **INSERT vs. INSERT:** Detect primary key collisions and secondary unique constraint violations. Implement configurable policy (`LWW`, `FLAG_FOR_REVIEW`, or rekeying for surrogate auto-increment keys).
  2. **UPDATE vs. DELETE (Tombstones):** Introduce tombstone entries in `_ss_change_log` (`op_type = 'DELETE'`). Implement `TOMBSTONE_POLICY` (`DELETE_WINS`, `UPDATE_RESURRECTS`, `FLAG_FOR_REVIEW`).
  3. **DELETE vs. DELETE:** Ensure concurrent deletes converge as an idempotent no-op without false-positive conflict generation.
  4. **Recoverable Conflict Persistence:** Ensure all flagged row mutations include complete before/after row snapshots in `MergeManager`.
- **Acceptance Criteria:**
  - `ConflictDetector` detects insert collisions and update-delete discrepancies.
  - New test file `test_mutation_conflicts.py` covering all row-mutation pairs passing 100%.

---

### Phase 3: Bounded Operations & N-Replica Validation
- **Objective:** Implement `BOUNDED_SUM` and test convergence across $N \ge 3$ replicas.
- **Dependencies:** Phase 2 complete.
- **Tasks:**
  1. Implement `BOUNDED_SUM` policy in `policy_registry.py` and `semantic_resolver.py`.
  2. Implement underflow safety check: if delta merge results in value $< \text{min\_bound}$, emit status `flagged` with audit explanation.
  3. Build multi-replica sync harness: simulate $N=3$ and $N=5$ replicas synchronizing in arbitrary sequential and interleaved orders.
  4. Measure and document convergence guarantees and order-dependencies.
- **Acceptance Criteria:**
  - `BOUNDED_SUM` correctly resolves within bounds and flags underflows in tests.
  - Multi-replica convergence test suite `test_n_replica_sync.py` passing 100%.

---

### Phase 4: Reproducible Benchmark Stress Harness
- **Objective:** Scale benchmark workloads from 9 synthetic cases to 1,000–10,000 operations.
- **Dependencies:** Phase 3 complete.
- **Tasks:**
  1. Build parametric synthetic workload generator in `backend/workloads/stress_harness.py`.
  2. Support configurable conflict densities ($5\%, 20\%, 50\%$) and dataset sizes ($10^3, 10^4$).
  3. Measure and export: $SCR$, $CR$, $VRA$, p50/p95/p99 latency, resolution overhead ($\Delta t$), and change log size.
  4. Expose endpoint `POST /api/v1/benchmark/stress` in `routes_benchmark.py`.
- **Acceptance Criteria:**
  - Automated stress benchmark runs reproducibly in under 30 seconds for 1,000 conflicts.
  - Baseline and SemanticSync receive strictly identical workloads.
  - Raw JSON and CSV telemetry exported for paper reproducibility.

---

### Phase 5: Relational Foreign Key Invariant Extension
- **Objective:** Detect and isolate foreign-key integrity violations during synchronization.
- **Dependencies:** Phase 2 and Phase 3 complete.
- **Tasks:**
  1. Enable SQLite foreign key checking during sync write-back (`PRAGMA foreign_keys = ON`).
  2. Implement orphan detection: catch foreign key constraint failures caused by parent deletions.
  3. Route orphaned child rows into a dedicated `_ss_quarantine` table with reference metadata.
  4. Provide manual recovery API: resolve orphan by re-linking to existing parent or deleting child.
- **Acceptance Criteria:**
  - Zero SQLite constraint errors crash the sync engine.
  - All orphaned child records quarantined durably and inspectable via API.
  - Dedicated test suite `test_foreign_key_invariants.py` passing 100%.

---

### Phase 6: Operational Log Compaction & Checkpoint
- **Objective:** Implement causal stability pruning for `_ss_change_log`.
- **Dependencies:** Phase 4 complete.
- **Tasks:**
  1. Track replica acknowledge vectors in `AppState`.
  2. Compute stable causal horizon: $T_{\text{stable}} = \min_{r} T_{\text{ack}}(r)$.
  3. Implement pruning routine: compact entries with $\text{HLC} < T_{\text{stable}}$ into base snapshot.
- **Acceptance Criteria:**
  - Change log storage reduced by $> 70\%$ following stable checkpointing.
  - Slow/lagging replicas are not broken by premature pruning.

---

### Phase 7: Studio Integration & Research Release
- **Objective:** Complete end-to-end user experience and publish academic research package.
- **Dependencies:** Phases 1–6 complete.
- **Tasks:**
  1. Integrate new conflict types (orphans, tombstones, bound violations) into Studio `Conflicts.jsx`.
  2. Hook stress benchmark telemetry into Studio `Analytics.jsx`.
  3. Finalize complete documentation package and paper manuscript.
- **Acceptance Criteria:**
  - Studio UI builds cleanly and renders all metrics live.
  - End-to-end regression test suite passing 100%.
