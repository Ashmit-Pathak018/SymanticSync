# SemanticSync — Prioritized Phased Implementation Plan

**Version:** 2.0 (Reconciled)  
**Status:** Approved Roadmap & Engineering Contract

---

## Phased Delivery Overview

```
Phase 0: Documentation Reconciliation               ✅ COMPLETE (This Step)
Phase 1: Core Correctness & Auditing               ✅ VERIFIED (tested scope)
Phase 2: Full Row-Mutation Conflict Model          ✅ VERIFIED (approved INSERT criteria; tested scope)
Phase 3: Bounded Operations & N-Replica Validation  ✅ VERIFIED (enumerated scope)
Phase 4: Reproducible Benchmark Stress Harness     ✅ VERIFIED (seeded 3×3 matrix; tested scope)
Phase 5: Relational Foreign Key Invariant Extension ✅ VERIFIED (tested scope)
Phase 6: Operational Log Compaction & Checkpoint   🚧 IMPLEMENTED FOR TESTED SCOPE — REVIEW PENDING
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
- **Closeout evidence:** Seeded generated policy properties, APPEND boundaries, representative invalid-input rollback, and `BEGIN IMMEDIATE` ordering are in `backend/tests/test_adversarial_resolution.py`. This verifies the tested input matrix, not every possible Python/SQLite value.

---

### Phase 2: Full Row-Mutation Conflict Model
- **Objective:** Expand conflict detection and resolution beyond cell-level UPDATE divergences.
- **Dependencies:** Phase 1 complete.
- **Tasks:**
  1. **INSERT vs. INSERT:** Detect primary-key and secondary-UNIQUE collisions as durable, reviewable conflicts preserving both complete row payloads. Permit explicit manual selection of either payload or a valid complete replacement payload. Apply the resolution atomically to both participating replicas, record an auditable operation, and leave the conflict unresolved on failed writes; retry must be safe after a committed database write if registry persistence fails. Refuse stale/missing participant rows and rows with declared foreign-key dependents until dependent-data behavior is defined. Automatic LWW and re-keying are deferred until relational safety semantics are defined.
  2. **UPDATE vs. DELETE (Tombstones):** Introduce tombstone entries in `_ss_change_log` (`op_type = 'DELETE'`). Implement `TOMBSTONE_POLICY` (`DELETE_WINS`, `UPDATE_RESURRECTS`, `FLAG_FOR_REVIEW`).
  3. **DELETE vs. DELETE:** Ensure concurrent deletes converge as an idempotent no-op without false-positive conflict generation.
  4. **Recoverable Conflict Persistence:** Ensure all flagged row mutations include complete before/after row snapshots in `MergeManager`.
- **Acceptance Criteria:**
  - `ConflictDetector` detects insert collisions and update-delete discrepancies.
  - New test file `test_mutation_conflicts.py` covering all row-mutation pairs passing 100%.
- **Acceptance revision:** The original configurable-policy requirement is superseded by the approved manual-resolution criterion above. Automatic LWW and re-keying remain deferred until foreign-key effects, external references, identity stability, and preservation of dependent data are defined.
- **Closeout verification:** PK and secondary-UNIQUE selection, custom full-row replacement, transactional rollback on a second-replica failure or UNIQUE violation, durable conflict/audit records, restart recovery, stale local-edit protection, and idempotent retry are covered by `backend/tests/test_insert_collision_resolution.py`. This is schedule-specific evidence, not a general convergence guarantee.

---

### Phase 3: Bounded Operations & N-Replica Validation
- **Objective:** Implement bounded signed-delta operations and validate invariant safety plus selected $N \ge 3$ replica schedules. Tests do not establish general convergence.
- **Dependencies:** Phase 2 complete.
- **Tasks:**
  1. Implement `BOUNDED_SUM` policy in `policy_registry.py` and `semantic_resolver.py`.
  2. Use explicit policy syntax `BOUNDED_SUM[min=<number>,max=<number>]`; track finite signed deltas with stable operation IDs and inclusive bounds.
  3. Reject locally tracked writes outside bounds. During replay, atomically apply a delta only if the candidate remains in bounds; otherwise leave it unreceipted and report it as pending/rejected. Never clamp or discard the source operation.
  4. Deduplicate by operation identity; accept reordered bounded deltas when each next candidate remains safe. Exercise $N=3,5$ star, ring, and complete-pair schedules, reversed edge order, retries, duplicates, and restart.
  5. Document invariant safety separately from selected-schedule convergence. No general convergence guarantee is made; unsafe prefixes can remain pending until a safe operation/schedule permits retry.
- **Acceptance Criteria:**
  - `BOUNDED_SUM` respects inclusive floor and ceiling bounds, flags unsafe combined deltas, and never clamps.
  - Dedicated operation and N-replica suites pass for the schedules they enumerate; no claim of arbitrary-order convergence.
- **Closeout evidence:** `test_bounded_operations.py` and `test_n_replica_sync.py` cover the documented cases, including same-source reversed delta delivery. Full backend suite result is recorded in `TESTING_STRATEGY.md` and the Phase 3 traceability rows.

---

### Phase 4: Reproducible Benchmark Stress Harness
- **Objective:** Scale benchmark workloads from 9 synthetic cases to 1,000–10,000 operations.
- **Dependencies:** Phase 3 complete.
- **Tasks:**
  1. Build parametric synthetic workload generator in `backend/workloads/stress_harness.py`.
  2. Run the required $1{,}000, 5{,}000, 10{,}000$ operation sizes at $5\%,20\%,50\%$ conflicts using tracked writes and actual `sync_replicas()` calls.
  3. Compare identical seeded traces on LWW baseline and SemanticSync SUM. Define SCR as oracle-correct final values over all rows, VRA as oracle-correct conflicted rows, and CR as equal persisted values across the two replicas.
  4. Measure tracked-write p50/p95/p99, each actual sync duration, resolution overhead as SemanticSync sync duration minus baseline sync duration (may be negative), and change-log rows queried from both databases. Export all metrics, raw workload, and observed final states in JSON; export metrics and operation latencies in CSV.
  4. Expose endpoint `POST /api/v1/benchmark/stress` in `routes_benchmark.py`.
- **Acceptance Criteria:**
  - Automated stress benchmark runs reproducibly in under 30 seconds for 1,000 conflicts (must be measured; workload size and conflict count are reported separately).
  - Baseline and SemanticSync receive strictly identical workloads.
  - Tests recompute quality metrics from persisted observations and verify operation/log counts against the executed workload; full 3×3 matrix results are recorded before completion.
  - **Verified gate result:** Savepoint-batched receiver replay reduced the seed-42, 5,000-operation/20% trace (1,000 conflicts) to 16.097 s. Two additional same-seed runs measured 15.817 s and 15.915 s. All three are below 30 seconds. The optimized 3×3 matrix was rerun and exported; see `TESTING_STRATEGY.md` and `.codex-phase4-optimized-matrix-20261013/`. Evidence is specific to this seeded integer-SUM workload and host; it does not establish general convergence or production capacity.

---

### Phase 5: Relational Foreign Key Invariant Extension
- **Objective:** Detect and isolate foreign-key integrity violations during synchronization.
- **Dependencies:** Phase 2 and Phase 3 complete.
- **Tasks:**
  1. Enable SQLite foreign-key checking on every relevant tracked, receiver, API, query, and paired-resolution connection before opening write transactions.
  2. Discover child references by grouped FK metadata, including alternate unique referenced columns and composite key mappings; reject unsupported schemas before mutation.
  3. Quarantine nested dependent payloads and delete them before parent mutations in the same transaction; run `foreign_key_check` before commit.
  4. Restore the actual quarantined row on relink, verify its new parent relationship and row count, then update quarantine status in the same transaction.
  5. Cover local, received, paired, and API deletes plus received INSERT/UPDATE, restart, duplicate, and injected-failure cases.
- **Acceptance Criteria:**
  - Zero SQLite constraint errors crash the sync engine.
  - All orphaned child records quarantined durably and inspectable via API.
  - Dedicated test suite `test_foreign_key_invariants.py` passing 100%.
  - **Verified in tested scope:** focused FK suite passes 27 tests and the full backend suite passes 241 tests (one Starlette/httpx deprecation warning). Local, received, paired-engine, and API resolution delete paths, received INSERT/UPDATE rejection, alternate UNIQUE/composite FK dependencies, relink verification, restart, duplicate, and rollback cases are covered. Direct SQL is limited to FK rejection and does not invoke quarantine; engine row addressing rejects composite-PK target tables before mutation.

---

### Phase 6: Operational Log Compaction & Checkpoint
- **Objective:** Implement causal stability pruning for `_ss_change_log`.
- **Dependencies:** Phase 4 complete.
- **Tasks:**
  1. Persist per-replica acknowledgement vectors in `AppState`, keyed by stable operation ID and retaining source ID/sequence plus HLC.
  2. Compute $T_{\text{stable}} = \min_r T_{\text{ack}}(r)$ only after the exact operation-ID intersection is known for every currently enrolled replica. HLC is a strict cutoff, never delivery proof by itself.
  3. Use an explicitly provisioned `data/checkpoint_store.sqlite` as the durable source of truth for the journal, immutable manifest, captured ACK evidence, and full operation payload archive. Configure SQLite rollback journaling and `synchronous=FULL`; validate integrity, schema, identity, manifest hashes, snapshot hashes, and archived payload hashes before use. Startup never creates or repairs this store.
  4. Under one process-wide mutation/checkpoint lock, create consistent per-replica SQLite backup snapshots and bind each to exactly one member, replica ID/path/incarnation, membership epoch, user-schema and data fingerprints, exact operation-ID/payload-hash frontier, and stable HLC cutoff. Store the binding inside the snapshot as well as the hashed manifest. Commit `PREPARING`, archive, then `COMMITTED` before any replica pruning.
  5. Before ACK reconciliation or pruning, validate a one-to-one member/snapshot mapping; recompute each snapshot's integrity, schema/data fingerprints, and complete log/receipt frontier; compare its embedded identity and frontier with the manifest; and validate the live replica as that immutable snapshot plus a replay-verified tracked UPDATE/INSERT/DELETE tail. Tail operation IDs, local sequence order, causal dependencies, row preconditions, triggers, and final user data must validate. Unsupported tails or mismatched live data block recovery without pruning. Validate every member's ACK vector, incarnation, and durable registry evidence before persisting any ACK gap. A failed registry save rolls back its in-memory ACK mutation; retry reloads/compares the durable vector and verifies each successful publication. Prune each replica in a local `BEGIN IMMEDIATE` transaction, atomically recording compact receipts and the applied checkpoint marker. Resume committed/partial checkpoints idempotently after restart; any missing, duplicate, swapped, mismatched, or unverifiable snapshot blocks recovery without touching hot logs or ACK state.
  6. Existing offline members without ACKs pin the horizon. Replica creation refuses to overwrite an existing path; a recovered/reseeded replica must use a new path, while the original offline database and local operations remain preserved for review. The shared ancestor database is not rewritten.
- **Acceptance Criteria:**
  - A regression proves >70% `_ss_change_log` row-count reduction for a 13-operation acknowledged fixture; this is not a byte-level or workload-wide storage claim.
  - Missing/stale/offline/new replica ACKs pin the horizon; exact operation IDs and dependency closure are required. HLC is only a strict cutoff, never causal proof.
  - Missing/corrupt/unverifiable checkpoint state fails closed: no pruning, no automatic empty-store recreation, and a blocked status is surfaced. A checkpoint-store identity can be adopted from manifests only when replica membership/path/incarnation evidence agrees.
  - Crash/restart tests cover a committed manifest with tracked post-frontier UPDATE/INSERT/DELETE operations, invalid-tail rejection with unchanged ACKs/logs, a multi-member ACK conflict preflight, registry-save failure after in-memory ACK mutation with retry/restart, a blocked RESOLVE checkpoint alongside an unrelated valid checkpoint, a failure between replica prune transactions, snapshot/store corruption, six snapshot-binding rejection cases, and lock sharing. Invalid snapshots/conflicting ACK evidence must leave hot logs and ACK state unchanged. These are injected process-recovery and tested filesystem cases, not a power-loss certification.
  - Coordination remains single-process. Registry JSON, checkpoint SQLite, snapshots, and replica SQLite files do not share a global transaction. Manual recovery is required when evidence conflicts. Recovery validates post-frontier UPDATE/INSERT/DELETE tails by replaying onto a private snapshot copy and comparing final user data; tail IDs, sequence, dependencies, and row preconditions are checked. RESOLVE tails and unsupported/untracked edits block recovery and require manual review. An existing replica file is never overwritten by reseed.

**Phase 6 status:** **Approved and signed off for the documented tested scope (2026-10-13).** Reported verification: focused compaction/recovery suite **40 passed**; full backend suite **281 passed**, with one existing Starlette/httpx deprecation warning; `git diff --check` passed. These results were not rerun for this status-only sign-off update. The checkpoint store preserves full operation payloads and immutable per-replica snapshots, while each replica retains compact receipt metadata for dedupe. RESOLVE-tail recovery requires manual review; coordination is single-process; power-loss durability is not certified. No general convergence claim is made.

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
