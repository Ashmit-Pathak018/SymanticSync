# Correctness Model and Terminology

## Scope

SemanticSync is evaluated here as a Python/SQLite prototype with tracked mutation APIs, explicit pairwise synchronization, policy-specific conflict handling, and checkpoint-backed log compaction. The model does not assume an asynchronous network, simultaneous writers, Byzantine processes, arbitrary SQL, multiple server processes, or arbitrary replica counts unless a test explicitly constructs that case.

## Four distinct correctness questions

### Value correctness

A materialized value is correct when it matches the declared policy outcome under the policy's assumptions and the test's independent oracle. A flagged/rejected result is an outcome, not a materialized value. For the synthetic stress workload, the oracle is additive and only defines SUM-style conflicts: `base + delta_A + delta_B` for a row with two generated changes, and `base + delta_A` for a one-sided change.

The 2026-10-20 assignment-based engine pilot exposed an oracle-to-operation mismatch: if both replicas independently use absolute `SET` writes to the same non-base value, the state-diff detector considers there to be no conflict because the values are equal. The historical stress oracle nevertheless counts both generated deltas. For base 100 and two assignments of 110, it yields 120 while the engine retains 110. This remains a limitation of that historical SET workload. A separate `INCREMENT` operation has now been implemented and is covered by focused tests for two independent contributions, reverse delivery, duplicate replay after restart, large-integer precision, mixed SET conflicts, and post-checkpoint recovery; these finite tests do not retroactively validate or alter historical artifacts, nor establish arbitrary N-way convergence.

### Tracked increment state-transition model

For a supported numeric row/column, represent one replica's relevant state as `(v, R)`, where `v` is the stored value and `R` is the set of operation identities retained in its active change log or compacted-receipt ledger. An accepted local `INCREMENT(id, d)` transitions `(v, R)` to `(v + d, R ∪ {id})` only after the row update, stored-value readback, FK check, and operation-log insert succeed in one SQLite transaction. A received operation whose identity and payload match an existing receipt leaves state unchanged and is reported as a duplicate. Reuse of an identity with different operation metadata or payload is rejected. The active and compacted ledgers are both consulted for this decision.

For two replicas initialized from the same value `v0`, if the intended independent contributions are represented by distinct accepted operation identities `id_i`, and every such operation is delivered to each replica at most once in materialized state (with repeat deliveries resolved through receipts), the expected value is:

`v_final = v0 + Σ d_i`, for the set of distinct accepted increment identities.

This equation is the independent oracle for the tested additive cases; it does not apply to absolute assignments. `SET(110)` is an absolute replacement, not a contribution of `+10`; equal final assignment values do not encode intent and are not split into inferred deltas. When an increment and an absolute assignment conflict, the declared conflict policy governs the conflict; the regression suite uses `REJECT` and verifies both local values remain unchanged pending review. Integer additions outside SQLite's signed 64-bit range and non-finite floating-point inputs are rejected. These state-transition conditions describe the tested tracked path, not a proof for arbitrary histories, direct SQL, external writers, process concurrency, or every combination of `INCREMENT` with other operation kinds.

### Replica agreement

Agreement must name the compared projection. Stress RVAR compares the ordered `bench_rows.value` vectors from two replicas. Equal vectors do not establish equality of schemas, other tables, operation logs, receipts, quarantine state, ACKs, or checkpoints.

### Database convergence

Full database convergence would require equivalent state across every declared table and relevant metadata under a specified delivery schedule. The stress artifacts do not measure this. N-replica tests establish values and receipts for listed finite schedules only; no arbitrary-order or general convergence claim follows.

### History safety

History safety asks whether duplicate, reordered, stale, missing-dependency, malformed, invalid, or partially delivered operations preserve state and can be retried or are visibly blocked. The expected result may be apply-once, reject/pending, conflict for review, or fail closed. These outcomes must not be collapsed into a single success metric.

## State covered by these tests

When a regression claims preservation after failure, inspect and assert the relevant subset of:

- user rows and their SQLite storage values;
- `_ss_change_log` and operation identity;
- receipt and compacted-receipt ledgers;
- durable conflict/resolution records;
- quarantine payload and status;
- per-replica acknowledgement vectors;
- checkpoint journal, manifest, snapshot, and marker state;
- API status and rejected/blocked-operation details.

The exact checked state varies by test; tests in `research/correctness/TEST_COVERAGE_MATRIX.md` map it.

## Global assumptions and exclusions

- Operation replay requires tracked source history with operation identity and expected prior state.
- Synchronization is explicit and pairwise. Per-origin sequence values do not order unrelated source histories.
- The mutation/checkpoint lock is process-local. External SQLite connections can bypass it.
- SQL-console writes are not tracked; they are outside convergence, quarantine, and checkpoint-tail guarantees.
- SQLite connection-level FK enforcement and tested schema support constrain relational-integrity claims.
- Checkpoint recovery requires committed validated evidence; RESOLVE tails require manual review. Power-loss durability is not certified.
- Passing finite tests is evidence for enumerated inputs/schedules, not a proof of implementation correctness.
