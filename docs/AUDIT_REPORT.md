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

### 4.3 Remaining Boundaries at the Original Audit Snapshot
- **BOUNDED_SUM & Invariant Policies:** then assigned to Phase 3; see Phase 3 closeout below for the implemented bounded scope.
- **N-Replica Mesh Synchronization ($N \ge 3$ arbitrary topologies):** then assigned to Phase 3; arbitrary/general convergence remains unverified.
- **Foreign-Key Orphan Quarantine Table (`_ss_quarantine`):** Phase 5.
- **Change Log Compaction & Causal Stability Pruning:** Phase 6.



---

## 5. Phase 2 Adversarial Audit — Findings & Corrections (October 2026)

**Audit scope:** Causality, tombstones, UNIQUE constraints, composite-PK coverage.
**Approach:** Inspect-first, then add minimal targeted regression tests and fix confirmed bugs only.
**Outcome:** 3 confirmed bugs fixed, 8 new targeted tests added, 0 pre-existing tests broken.

### 5.1 Findings by Severity

#### HIGH — Composite-PK PRAGMA Bug (Fixed)

| | |
|---|---|
| **Location** | `conflict_detector.py`, `_get_pk_column()` |
| **Root Cause** | `pk == 1` was used instead of `pk > 0`. In SQLite PRAGMA, composite PKs assign `pk=1` for the first column and `pk=2, 3, ...` for subsequent. The old code matched only the first PK column and returned it as sole PK — composite-PK tables were **silently processed as single-PK**. |
| **Impact** | Detection results unreliable for composite-PK tables; row addressing via wrong single column. |
| **Fix** | `_get_pk_column` now collects all `pk > 0` columns; returns `None` when count ≠ 1. |
| **Verification** | `TestCompositePKSurfaced` (3 new tests). |

#### HIGH — Composite-PK Tables Silently Skipped Without Observable Signal (Fixed)

| | |
|---|---|
| **Location** | `conflict_detector.py`, `detect()` return type |
| **Root Cause** | `continue` silently dropped composite-PK tables with no caller-visible signal. |
| **Fix** | `detect()` now returns `DetectResult(conflicts, skipped_tables)` (NamedTuple). `SyncResult` extended with `skipped_tables: list[str]`. All callers updated. |

#### MEDIUM — `DELETE_WINS` Silent Error Swallowing (Fixed)

| | |
|---|---|
| **Location** | `crdt_sync.py`, `sync_replicas()` `DELETE_WINS` branch |
| **Root Cause** | `except Exception: pass` on both deletes; `auto_resolved` incremented unconditionally. |
| **Impact** | A failed delete was still reported as auto-resolved — silent data loss. |
| **Fix** | Only `RuntimeError("…not found…")` suppressed (idempotent). Other failures set `delete_succeeded = False`; conflict moved to `flagged_conflicts`. `auto_resolved` incremented only after both deletes succeed. |

#### MEDIUM — UPDATE Timestamp Used Wrong Key in Cases 3 & 4 (Mitigated)

| | |
|---|---|
| **Location** | `conflict_detector.py`, Cases 3 & 4 |
| **Root Cause** | `ts_key_row = (table, row_id, "*")` missed UPDATE timestamps (`apply_change` writes actual column name, not `"*"`). |
| **Mitigation** | New `_get_row_update_ts()` helper scans all non-PK columns for the minimum UPDATE timestamp. Used in Cases 3 & 4 for accurate timestamp context in conflict records. |

#### MEDIUM — Causality Not Distinguished in UPDATE vs DELETE (Documented Limitation)

| | |
|---|---|
| **Audit Finding** | State-based snapshot diffing cannot distinguish causally ordered DELETE from concurrent DELETE without vector clocks. |
| **Decision** | Conservative: Cases 3 & 4 still flag all UPDATE+DELETE pairs. `op_map` last-op type now included in `explanation` string for reviewer context. Accurate timestamps recorded via `_get_row_update_ts`. |
| **Documentation** | `KNOWN_LIMITATIONS.md` §11; `TestCausalityDocumented` (3 new tests). |

#### LOW — Stale Replica Tombstone Propagation Gap (Historical Finding; Addressed in Phase 2.1/2.2)

| | |
|---|---|
| **Original Finding** | Snapshot detection alone did not report an unchanged stale copy as a conflict. |
| **Current Behavior** | Pairwise sync delivers the latest row operation when it is DELETE; later UPDATE/INSERT operations supersede older deletes. Delivery is identity-aware and atomic. Locally changed receiver rows are retained for conflict review. |
| **Verification** | Phase 2.2 relay, restart, duplicate, reinsert, concurrency, and atomic rollback tests. |

---

### 5.2 Files Changed

| File | Change |
|---|---|
| `backend/engine/conflict_detector.py` | Fixed composite-PK PRAGMA bug (`pk > 0`); `DetectResult` NamedTuple return; `_get_row_update_ts()` helper; improved Cases 3/4 timestamps and explanations |
| `backend/engine/crdt_sync.py` | Unpacks `DetectResult`; fixed `DELETE_WINS` error handling; `skipped_tables` in `SyncResult` |
| `backend/tests/test_mutation_conflicts.py` | All `detect()` calls updated; 8 new adversarial regression tests |

---

### 5.3 Historical Phase 2 Adversarial Audit Test Metrics

These counts describe the suite immediately after the Phase 2 audit, before Phase 2.1/2.2 tests were added.

| Metric | Phase 2 Pre-Audit | Phase 2 Post-Audit |
|---|---|---|
| Total tests | 92 | **100** |
| Passing | 92 | **100** |
| Failing | 0 | **0** |
| New adversarial tests | — | **8** |
| Duration | ~1.2 s | ~1.4 s |

---

### 5.4 Remaining Limitations

- Causality auto-detection in UPDATE vs DELETE requires vector clocks (not in scope).
- Tombstone delivery runs during explicit pairwise sync; no background replica mesh is provided.
- Composite-PK tables fully unsupported; tracked in `skipped_tables`.
- BOUNDED_SUM selected schedules and N=3/5 mesh validation have since been implemented; arbitrary convergence remains unverified. Foreign-key quarantine remains Phase 5; log compaction remains Phase 6.

## 6. Phase 2.1 Hardening (October 2026)

- **Durable tombstones:** Pairwise sync reads recorded DELETE snapshots and applies them to matching rows only when the receiver has no logged operation for that row. The receiving replica records its own DELETE, so later pairwise sync can relay it. Repeated sync does not create duplicate tombstones.
- **Delayed delivery safety:** A receiver with any explicit local row operation is not automatically deleted; normal UPDATE-vs-DELETE detection preserves it for review. No timestamp-gap heuristic is used.
- **Conflict API error handling:** Removed silent exception swallowing during resolution write-back. Failures are reported as HTTP errors; composite-PK write-back is rejected instead of using the first PK column.
- **Composite-PK observability:** Conflict detection endpoint continues returning its existing list payload and includes skipped table names in `X-SemanticSync-Skipped-Tables`.
- **Regression coverage:** Focused mutation suite: 19 passed. Full backend suite: 101 passed (one existing Starlette/httpx deprecation warning).

## 7. Phase 2.2 Integrity Fixes (October 2026)

- **Superseded tombstones:** A DELETE is eligible for delivery only when it is the latest logged row operation. Origin operation identity is preserved through relays; a later INSERT or UPDATE prevents replay of the older tombstone.
- **Atomic delivery:** The receiver checks the origin identity, local operations, primary key, and row snapshot under `BEGIN IMMEDIATE`; row deletion and the durable receiver tombstone commit together. Concurrent writers serialize before validation. A durable `sequence` column records append order and is migrated from existing log rowids.
- **Composite keys:** The sync engine rejects composite primary keys in direct mutation and tombstone delivery paths. Unsupported tables remain visible in sync API responses and SyncHub.
- **Conflict resolution:** Both API and engine resolution paths update both replica files in one attached-database transaction and log a shared operation identity. Row-level `None` explicitly deletes; cell-level `None` writes SQL NULL. Missing rows or write failures roll back both and leave the conflict unresolved.
- **Regression coverage:** Added 16 tests covering relay in both directions, restart persistence, reinsert supersession, duplicate identity, concurrent writer, rollback in API and engine, composite-key, missing-row, ignored deletes, WAL rejection, delete/null, and sync API response. Full backend suite: 117 passed, one existing deprecation warning.

## 8. Phase 2.3 Operation Propagation (October 2026)

- **Implementation:** Pairwise sync replays INSERT, UPDATE, and DELETE operations with stable origin identity and originating source sequence. Receiver mutation and receipt logging share a transaction; per-source sequence fencing rejects older delayed operations.
- **Safety boundary:** Operations apply only when expected row state is present. A divergent tracked change stops propagation for that row for conflict review. This is not evidence of general multi-replica convergence; cross-source histories, untracked SQL edits, schema drift, complex scalar serialization, and trigger side effects remain limitations.
- **Regression evidence:** Focused integrity and mutation-conflict suites: 38 passed. Full backend suite: 120 passed, one existing Starlette/httpx deprecation warning. Frontend production build succeeded. `git diff --check` and Python byte-compilation succeeded.

## 9. Phase 2.4 Integrity Review (October 2026)

- **INSERT receipt integrity:** Receiver re-reads and compares the complete stored row with the operation payload. Ignored and row-mutating trigger regressions verify the mutation and receipt both roll back.
- **Resolution propagation:** RESOLVE records share an operation ID, canonical source ID, source sequence, causal dependencies, and expected peer snapshots. Both peer relay directions to a third replica are tested; rejected operations are returned in sync results.
- **Retry evidence:** A forced failure after one operation commits is followed by a successful retry; the earlier receipt is deduplicated and the outstanding operation applies.
- **Verification:** Focused integrity and mutation-conflict suites: 45 passed. Full backend suite: 127 passed, one existing Starlette/httpx deprecation warning. Frontend production build succeeded; `git diff --check` passed.
- **Scope:** These tests validate selected schedules, not general convergence. Direct SQL changes, nondeterministic triggers, arbitrary cross-source histories, and external trigger side effects remain outside the guarantee.

### Phase 2.4 Final Fix (October 2026)

- **Audit finding addressed:** `UPDATE_RESURRECTS` now flags missing or non-dictionary winner payloads as unresolved before any write, resolution log, success count, or applied-change entry.
- **Relay evidence strengthened:** Third-replica tests now assert persisted resolution identity/source sequence/dependencies match both peers and duplicate relay creates exactly one receipt.
- **Regression coverage:** Added invalid-payload cases asserting both replica rows and change-log counts remain unchanged.
- **Verification:** Focused integrity and mutation-conflict suites: 47 passed. Full backend suite: 129 passed with one existing Starlette/httpx deprecation warning. Frontend build succeeded; `git diff --check` passed. No general convergence claim is made.

## 10. Phase 1/2 Roadmap Closeout (October 2026)

- **Phase 1 evidence:** Added reproducible seeded generated properties across all resolver policies, valid associativity/idempotence checks, explicit AVG non-associativity and SUM non-idempotency examples, APPEND empty/Unicode/None/repeat-sync coverage, invalid-input rollback checks, and trace-verified `BEGIN IMMEDIATE` for local tracked mutations.
- **Phase 2 evidence:** Persist/reload regression now covers every flagged row-mutation conflict class (PK INSERT, secondary UNIQUE, UPDATE/DELETE); DELETE/DELETE agreement remains conflict-free. Existing policy/tombstone, relay, and atomicity regressions remain passing.
- **Phase 2 acceptance at this historical closeout:** INSERT collisions were review-only; configurable LWW/re-key behavior was not implemented. The 143-test verification was the result at that point, before the acceptance revision was approved and manual resolution was implemented.
- **Historical verification:** Focused closeout suites: 61 passed. Full backend suite: 143 passed with one existing Starlette/httpx deprecation warning. `git diff --check` passed.
- **Scope at that historical closeout:** The selected tests did not establish general N-replica convergence. Phase 3 was then unimplemented and depended on closing or formally revising Phase 2 acceptance.

## 11. Approved Manual INSERT-Collision Resolution (October 2026)

- **Acceptance revision implemented:** PK and secondary-UNIQUE INSERT conflicts remain durable and reviewable with both full row snapshots. Reviewers can select either payload or submit a complete replacement payload.
- **Write safety:** Both participating replicas are changed in one rollback-journal attached-database transaction. Current participant rows are validated against the captured snapshots; UNIQUE violations, trigger failures, missing/mutated rows, and schema mismatch roll back without marking the conflict resolved.
- **Audit and recovery:** Resolution receipts have stable operation identity and source sequence in both change logs. Conflict registry writes use a same-directory atomic replace. If registry persistence fails after the replica transaction commits, retry recognizes the existing receipt and completes conflict-status persistence without duplicating the operation.
- **Limitations:** This operation kind is not replayable to a third replica yet; sync reports it as rejected. Automatic LWW/re-key remains deferred. Tests cover selected pairwise schedules, not general convergence.
- **Verification:** Focused INSERT-collision, integrity, and mutation-conflict suites: 58 passed. Full backend suite: 153 passed with one existing Starlette/httpx deprecation warning. `git diff --check` passed.

## 12. Phase 3 BOUNDED_SUM and Mesh Validation (October 2026)

- **Implementation:** `BOUNDED_SUM[min=...,max=...]` records finite inclusive bounds and signed deltas with stable operation IDs. Tracked writes outside the bounds fail before data/log mutation. Unsafe replay candidates remain pending in the source log and are reported without clamping or receipt.
- **Safety and delivery:** Bounded delta replay is additive and deduplicated by operation identity. Same-source deltas can be delivered in reversed order; each immediate candidate must remain inside bounds. Direct SQL bypasses tracked validation and lacks operation identity.
- **Evidence:** `test_bounded_operations.py` (16 cases) and `test_n_replica_sync.py` (12 N=3/5 schedule variants) cover boundaries above $2^{53}$, ignored/mutating trigger rollback, overflow/underflow, pending/retry receipt identity, restart, duplicates, reversed delivery, and star/ring/complete pair schedules.
- **Scope:** The tested safe schedules preserve invariant bounds and one receipt per operation. They do not establish general convergence, arbitrary delivery-order safety, offline partition recovery, or protection against untracked SQL writes.
- **Verification after Phase 3.1 fixes:** Focused suites 28 passed; full backend suite 181 passed with one existing Starlette/httpx deprecation warning; `git diff --check` passed.

### Phase 3.2 Targeted Fixes (October 2026)

- **BOUNDED_SUM auto-resolution in API:** `POST /api/v1/conflicts/resolve` with `resolution_mode="auto"` now extracts `min_bound` and `max_bound` via `parse_bounded_sum_bounds()` and passes them to `SemanticResolver.resolve`. Inclusive bounds are also enforced during write-back in `_write_resolution_atomically`. Tested via `test_bounded_sum_auto_resolution_via_api`.
- **Delivery-trigger safety:** Verified that incoming bounded operation delivery on a replica with an ignored trigger (`RAISE(IGNORE)`) or mutating trigger (`AFTER UPDATE ... SET amount=999`) rolls back atomically without modifying the row state or recording a change log receipt (`test_bounded_delivery_trigger_rolls_back_without_receipt`).
- **REAL-affinity precision safety:** Verified that writing an integer above $2^{53}$ into a column declared with SQLite `REAL` affinity fails post-write validation due to float64 precision loss and rolls back, leaving both table data and change log unchanged (`test_bounded_sum_real_affinity_rejects_lossy_integers`).
- **Three-way large-integer divergence:** Verified concurrent divergent changes above $2^{53}$ on both replicas perform exact additive merge within bounds, and that out-of-bounds combined candidates remain safely flagged for review without mutating replicas (`test_three_way_large_integer_divergence`).
- **Verification:** Focused bounded suite: 21 passed (33 including mesh suite); full backend suite: 186 passed with one existing Starlette/httpx deprecation warning; `git diff --check` passed.

### Phase 3.3 Correctness Fixes (October 2026)

- **BOUNDED_SUM RESOLVE replay validation:** In `CRDTSyncEngine._apply_received_operation`, incoming `RESOLVE` operations affecting a `BOUNDED_SUM` column require bounds metadata. Rejects with `"requires bounds metadata"` if bounds are missing, or `"do not match policy bounds"` if bounds conflict with the configured policy, before applying writes or receipts. `test_bounded_resolve_relay_rejects_missing_bounds` and `test_bounded_resolve_relay_rejects_mismatched_bounds` verify state and receipts remain untouched.
- **HTTP client coverage for `/api/v1/conflicts/resolve`:** `test_conflicts_resolve_api_endpoint` in `test_api.py` verifies the resolution endpoint through `TestClient`: auto resolution on bounded sums, out-of-bounds flagged resolutions, 404 on missing conflicts, 400 on invalid modes, 400 on auto-resolution of INSERT collisions, and strict JSON response serialization.
- **Overflow operation identity and receipts:** Extended `test_three_way_large_integer_divergence` to explicitly verify that rejected overflow operations record exact operation IDs in `rejected_operations`, `"BOUNDED_SUM pending"` in reasons, maintain exactly one receipt on the originating replica, zero foreign receipts on peers, and remain idempotent across repeated synchronizations.
- **Safe atomic state save and retry cleanup:** Enhanced `AppState.save()` so cleanup failures (`os.unlink(temporary_path)`) during exception handling never mask the underlying `PermissionError` or `OSError`. Verified retry exhaustion (10 retries), immediate unrelated `OSError` propagation, and unmasked original errors via `test_state_save_retry_exhaustion_unrelated_errors_and_cleanup`.
- **Verification:** Focused bounded and mesh suites: 35 passed; full backend suite: 190 passed with one existing Starlette/httpx deprecation warning; `git diff --check` passed.

### Phase 3.4 Final Fixes (October 2026)

- **Bounded RESOLVE idempotency:** Both `_write_resolved_pair` in `crdt_sync.py` and `_write_resolution_atomically` in `routes_conflicts.py` now explicitly persist `bounds_min` and `bounds_max` columns when recording a `RESOLVE` operation for a bounded column. In `crdt_sync.py`, `_apply_received_operation` logs `receipt_min` and `receipt_max` consistently. `test_valid_bounded_resolution_relay_is_idempotent` relays a valid bounded resolution twice, verifying exactly one receipt exists, target replica state remains unchanged on subsequent delivery, and no rejection is triggered.
- **API overflow state verification:** Extended `test_conflicts_resolve_api_endpoint` in `test_api.py` to assert that when an out-of-bounds `BOUNDED_SUM` resolution is flagged for review, both participating replicas' database values remain unchanged.
- **Testing documentation reconciliation:** Marked historical Phase 3.1 count (181 passed: 16 bounded, 12 mesh) and documented current counts: 24 bounded cases in `test_bounded_operations.py`, 12 mesh cases in `test_n_replica_sync.py` (36 focused suite passed), and 191 total tests passing in the full backend suite.
- **Verification:** Focused bounded and mesh suites: 36 passed; full backend suite: 191 passed with one existing Starlette/httpx deprecation warning; `git diff --check` passed.


