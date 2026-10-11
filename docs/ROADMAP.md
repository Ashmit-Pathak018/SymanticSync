# SemanticSync — Strategic Roadmap

**Version:** 2.0 (Reconciled)  
**Status:** Approved Technical Trajectory

---

## Phased Release Trajectory

```
v0.1.0  ✅  Backend Core & REST API (Completed)
v0.2.0  ✅  Documentation Suite & Reconciled Specs (Completed)
v0.2.1  ✅  SemanticSync Studio Frontend Integration (Merged PR #1)
v0.3.0  📋  Phase 1: Core Correctness & Property-Based Adversarial Tests
v0.4.0  📋  Phase 2: Full Row-Mutation Model (INSERT, DELETE, Tombstones)
v0.5.0  📋  Phase 3: BOUNDED_SUM Invariants & N-Replica Convergence
v0.6.0  📋  Phase 4: Scaled Reproducible Benchmark Suite (1,000–10,000 ops)
v0.7.0  📋  Phase 5: Foreign Key Referential Integrity & Orphan Quarantine
v0.8.0  📋  Phase 6: Causal Stability Change-Log Compaction
v1.0.0  📋  Phase 7: Studio Hardening, Artifact Release & Research Publication
```

---

## Detailed Milestone Objectives

### Next Milestone: v0.3.0 (Phase 1 — Core Correctness)
- Property-based tests verifying commutativity for all symmetric policies.
- Boundary condition validation: zero, negative deltas, empty text, unicode delimiters.
- Strict transactional write-back locking with parameterized SQLite queries.

### Upcoming Milestone: v0.4.0 (Phase 2 — Full Row-Mutation Conflict Model)
- Primary-key and secondary UNIQUE constraint conflict detection on concurrent insertions.
- `UPDATE vs DELETE` tombstone conflict detection and resolution policies (`DELETE_WINS`, `UPDATE_RESURRECTS`, `FLAG_FOR_REVIEW`).
- Idempotent `DELETE vs DELETE` convergence.
- Rich row-level conflict recovery in `MergeManager`.

### Mid-Term Milestone: v0.5.0 (Phase 3 — Bounded Invariants & N-Replicas)
- Implementation of `BOUNDED_SUM` policy with floor/ceiling checks (`min_val=0`).
- Multi-replica mesh testing ($N=3, 5$) under arbitrary synchronization orderings.
- Formal documentation of convergence boundaries under non-idempotent operators.

### Scaled Evaluation Milestone: v0.6.0 (Phase 4 — Scaled Benchmark Suite)
- Parametric synthetic workload generation ($1,000$ to $10,000$ operations).
- Controlled conflict densities ($5\%, 20\%, 50\%$).
- Automated telemetry export: SCR, CR, VRA, p50/p95/p99 latency, and resolution overhead.

### Relational Extension Milestone: v0.7.0 (Phase 5 — Foreign Key Integrity)
- Foreign key constraint enforcement (`PRAGMA foreign_keys = ON`).
- Non-destructive orphan quarantine via `_ss_quarantine` table.
- Quarantine inspection and resolution APIs.

### Operational Hardening: v0.8.0 (Phase 6 — Causal Log Compaction)
- Stable horizon checkpointing based on minimum acknowledged replica HLC timestamps.
- Automated compaction of `_ss_change_log` entries.

### Research Release: v1.0.0 (Phase 7 — Academic Manuscript & Open Source Release)
- Studio telemetry dashboard hooks for all metrics.
- Complete reproducibility package and paper manuscript submission.
