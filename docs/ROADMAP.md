# SemanticSync — Strategic Roadmap

**Version:** 2.0 (Reconciled)  
**Status:** Approved Technical Trajectory

---

## Phased Release Trajectory

```
v0.1.0  ✅  Backend Core & REST API (Completed)
v0.2.0  ✅  Documentation Suite & Reconciled Specs (Completed)
v0.2.1  ✅  SemanticSync Studio Frontend Integration (Merged PR #1)
v0.3.0  ✅  Phase 1: Core Correctness & Generated Adversarial Tests (tested scope)
v0.4.0  ✅  Phase 2: Row-Mutation Model verified for approved manual INSERT-collision criteria
v0.5.0  ✅  Phase 3: BOUNDED_SUM invariant safety & selected N-replica schedules (tested scope)
v0.6.0  ✅  Phase 4: Real replica benchmark matrix and measured performance gate (tested scope)
v0.7.0  ✅  Phase 5: FK write-path integrity verified for tested scope (latest focused audit: 34 passed; full-suite count 241 is historical)
v0.8.0  ✅  Phase 6: Causal Stability Change-Log Compaction (approved for documented tested scope)
v1.0.0  📋  Phase 7: Studio Hardening, Artifact Release & Research Publication
```

---

## Detailed Milestone Objectives

### Phase 1 Closeout: v0.3.0 (Core Correctness)
- Property-based tests verifying commutativity for all symmetric policies.
- Boundary condition validation: zero, negative deltas, empty text, unicode delimiters.
- Strict transactional write-back locking with parameterized SQLite queries.

### Upcoming Milestone: v0.4.0 (Phase 2 — Full Row-Mutation Conflict Model)
- Primary-key and secondary UNIQUE constraint conflict detection on concurrent insertions.
- `UPDATE vs DELETE` tombstone conflict detection and resolution policies (`DELETE_WINS`, `UPDATE_RESURRECTS`, `FLAG_FOR_REVIEW`).
- Idempotent `DELETE vs DELETE` convergence.
- Rich row-level conflict recovery in `MergeManager`.
- Durable, reviewable PK and secondary-UNIQUE collision conflicts preserve both complete payloads and support explicit selection or complete replacement across the two participating replicas.
- Automatic LWW and re-key remain deferred until relational safety semantics are defined. Manual collision-resolution relay to a third replica is not implemented.

### Mid-Term Milestone: v0.5.0 (Phase 3 — Bounded Operations & N-Replicas)
- `BOUNDED_SUM[min=<number>,max=<number>]` tracks signed deltas with stable IDs, duplicate suppression, and inclusive bounds.
- Locally invalid writes are rejected. Unsafe replay candidates remain pending and are reported; values are never clamped and source operations are retained.
- Tests cover $N=3,5$ star, ring, and complete-pair schedules, reversed edge order, duplicate delivery, and restart.
- Evidence is schedule-specific. Invariant checking protects tracked writes and replay materialization; it does not prove general convergence or protect direct SQL edits.

### Scaled Evaluation Milestone: v0.6.0 (Phase 4 — Scaled Benchmark Suite)
- Run actual tracked writes and `sync_replicas()` on isolated SQLite replicas for 1,000, 5,000, and 10,000 operations at 5%, 20%, and 50% conflicts.
- Compare the same seeded operations under LWW baseline and SemanticSync SUM; compute conflict-only SCR from the explicit oracle. Report benchmark-row value agreement separately; it compares only `bench_rows.value`, not complete replica state. Stress VRA is N/A because no domain range/FK constraints are modeled.
- Measure tracked-write p50/p95/p99, actual sync time, delta overhead, and change-log counts; export raw workload, observations, and metrics to JSON and metrics/timings to CSV.
- The optimized 3×3 matrix ran real tracked writes and syncs and exported observations/metrics. Savepoint-batched receiver replay reduced the seed-42 5,000-op/20%-conflict case from 62.52 s to 16.097 s; two repeated same-seed runs measured 15.817 s and 15.915 s. All three meet the under-30-second/1,000-conflict gate. Phase 4 is verified for this tested synthetic SUM scope only; this does not establish general convergence or production capacity.

### Relational Extension Milestone: v0.7.0 (Phase 5 — Foreign Key Integrity)
- Enable `PRAGMA foreign_keys = ON` before transactions on tracked, received, pair-resolution, query, conflict, and quarantine connections.
- Atomically quarantine nested dependent rows before parent deletion; verify FK integrity before committing.
- Discover grouped/composite FK mappings and alternate unique referenced columns; reject unsupported identities before mutation.
- Relink by restoring the actual quarantined child under a verified parent; mark resolved only after successful insert and FK validation.
- A historical Phase 5 gate reported 241 backend passes, including 27 FK tests. In the 2026-10-15 claim audit, the focused FK suite passed 34 tests in 1.40s; the full backend suite was not completed, so the 241 count remains historical. Earlier post-Phase 6 counts of 253 and 262 are also historical, not current verification. Local tracked, received, paired, and API resolution writes, rollback, nested dependencies, alternate UNIQUE references, composite child keys, duplicate delivery, restart, and safe relink are covered in selected cases. Composite-PK mutation targets are rejected before mutation. Direct SQL does not enter the quarantine workflow; FK checks prevent invalid deletes on the guarded SQL console connection.

### Operational Hardening: v0.8.0 (Phase 6 — Causal Log Compaction)
- Persist exact per-replica operation acknowledgements and apply the strict HLC horizon only after operation-ID and dependency evidence.
- Use an explicitly initialized SQLite checkpoint journal, full payload archive, hashed per-replica snapshots, fail-closed validation, and idempotent recovery around per-replica pruning.
- Share a single-process lock between tracked mutations and snapshot capture. Existing replica files cannot be overwritten during reseeding; returning offline tails require separate-path recovery and review.
- **Phase 6 complete for the documented tested scope (2026-10-15).** Original user-reported results: focused `test_log_compaction.py` **41 passed in 3.30s**; full backend suite **309 passed, 1 warning in 75.06s**. Supplemental local verification on 2026-10-20 completed with **42 focused tests passed in 4.41s** and **332 backend tests passed, 1 warning in 77.43s**. This is not a new acceptance audit or scope expansion. RESOLVE-tail recovery requires manual review; coordination is single-process; power-loss durability is not certified; no general convergence guarantee is made. Phase 7 remains unchanged and has not started. See `IMPLEMENTATION_PLAN.md`, `TRACEABILITY_MATRIX.md`, and `KNOWN_LIMITATIONS.md` for tested scope and evidence.

### Research Release: v1.0.0 (Phase 7 — Academic Manuscript & Open Source Release)
- Studio telemetry dashboard hooks for all metrics.
- Complete reproducibility package and paper manuscript submission.
