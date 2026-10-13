# SemanticSync — Known Limitations & System Boundaries

**Version:** 2.0 (Reconciled)  
**Status:** Verification Baseline

---

## 1. Engine Boundaries & Current Scope (Phase 1 Baseline)

### 1. Single-Column Primary Key Requirement
- The current `ConflictDetector` identifies records via a single primary key column detected via `PRAGMA table_info`.
- Tables with composite primary keys (multi-column PKs) are skipped during conflict discovery.
- **Remediation:** Composite-PK tables remain unsupported and are surfaced as skipped. Tuple-based addressing is not included in the original seven-phase acceptance criteria; no phase assignment is claimed.

### 2. Full Row Mutation Conflict Model (Implemented in Phase 2)
- Prior to Phase 2, `ConflictDetector` skipped missing rows and evaluated only `UPDATE vs UPDATE`.
- **Status:** **Implemented & Verified.** The detector now handles the complete relational mutation lifecycle:
  - `INSERT vs INSERT`: PK collisions with divergent payloads are detected and flagged; identical duplicate insertions converge idempotently.
  - `INSERT vs INSERT` (UNIQUE constraint): Secondary unique index collisions across differing PKs are detected and flagged.
  - **Verified manual resolution:** PK and secondary-UNIQUE INSERT collisions are persisted as reviewable conflicts with both complete payloads. A reviewer can select either payload or provide a complete replacement; the attached-database write and resolution log are transactional across the two participating replicas. Failed writes roll back, and retry recognizes the stable resolution receipt. Stale/missing participant rows and rows with declared FK dependents are refused. Automatic LWW and re-key remain deferred pending foreign-key, external-reference, identity-stability, and dependent-data semantics. Manual collision-resolution relay to a third replica is not implemented; sync rejects the unknown resolution operation kind rather than applying it.
  - `UPDATE vs DELETE`: Concurrent update and delete are flagged by default; configurable via `DELETE_WINS` and `UPDATE_RESURRECTS` tombstone policies.
  - `DELETE vs DELETE`: Idempotent convergence without conflict across 2 and 3 replicas.

### 3. Additive Delta Independence Assumption
- The `SUM` operator formula ($V_{\text{base}} + \Delta_A + \Delta_B$) assumes both replicas performed independent delta modifications relative to the ancestor base snapshot.
- If both replicas performed absolute assignments (e.g. `SET balance = 50` rather than `SET balance = balance - 50`), additive reconciliation is semantically invalid.
- `BOUNDED_SUM` now provides an explicit bounded signed-delta path; ordinary `SUM` remains unbounded and can still underflow or overflow.

### 4. Non-Associativity of `AVG`
- Arithmetic mean is commutative ($A \sqcup B = B \sqcup A$) but strictly **non-associative**:
  $$\text{avg}(\text{avg}(A, B), C) \neq \text{avg}(A, \text{avg}(B, C))$$
- `AVG` is valid only for pairwise reconciliations where both values represent simultaneous sensor observations. It cannot serve as an arbitrary multi-replica mesh CRDT operator without state tuples $\langle \text{sum}, \text{count} \rangle$.

### 4a. APPEND Algebraic Boundary
- Pairwise APPEND orders two divergent strings by replica ID, so the tested pair operation is commutative when values remain paired with their replica IDs. Identical current strings are returned once.
- This does not make APPEND an associative, idempotent N-way join: a merged string loses its original contribution set, and re-merging materialized text with stale values can duplicate or reorder content. The repeat-sync regression verifies one tracked pairwise schedule only.

### 5. Pairwise Synchronization Model
- `CRDTSyncEngine.sync_replicas()` currently synchronizes two replicas ($R_A \leftrightarrow R_B$) against a shared base snapshot.
- Mesh topology sync still consists of sequential pairwise calls. Phase 3 verifies selected BOUNDED_SUM schedules for N=3/5; this does not establish arbitrary-order convergence.

---

## 2. Relational & Operational Limitations

### 5a. Phase 4 Benchmark Interpretation
- The remediation harness runs real tracked `apply_change` calls and pairwise `sync_replicas()` on isolated SQLite files. The current trace uses integer SUM deltas; it is not a representative distribution of all SemanticSync policies or application workloads.
- The baseline is the same generated trace synchronized under LWW. SCR/VRA compare each persisted replica value against an explicit additive oracle; CR counts matching persisted values between the two replicas. Latency percentiles cover tracked writes, and resolution overhead is SemanticSync sync time minus LWW sync time; negative overhead is valid.
- The optimized matrix and repeated gate results are tied to seed 42, this host, and the uncommitted working tree; they do not establish general convergence, production capacity, or statistical confidence. The original 5,000-operation/20% case measured 62.52 seconds; after replay savepoint batching it measured 16.097 seconds, with same-seed repeats at 15.817 and 15.915 seconds. The full optimized 3×3 matrix is exported to `.codex-phase4-optimized-matrix-20261013/`.

### 6. Foreign Key Constraints
- **Status: Verified for tested write paths.** Tracked local and received deletes, paired engine/API resolution deletes, conflict resolution, query, and quarantine connections enable `PRAGMA foreign_keys = ON` before write transactions. Nested child payloads are quarantined in the same transaction before destructive parent changes, and `foreign_key_check` runs before commit.
- FK discovery groups composite references and uses each declared referenced column, including alternate UNIQUE parent keys. Composite row identities are preserved in quarantine. Engine mutation/sync entry points still require a single-column row key and must reject unsupported target tables before mutation.
- Relinking now inserts the quarantined child with its FK updated to an existing parent; a failed insert or FK check leaves status unresolved. Confirmation of deletion retains the payload in quarantine for audit.
- Tests cover the currently enumerated local/received/pair/API resolution delete paths, nested descendants, alternate unique parent keys, composite child/FK mappings, restart persistence, duplicate delivery, rejected received FK writes, and injected rollback. Historical Phase 5 gate: 241 passed; pre-checkpoint Phase 6 suite: 253 passed; previous full backend suites: 262, 268, 275, and 277 passed; current full backend suite: 281 passed, with one Starlette/httpx deprecation warning. This verifies tested code paths, not every possible schema/trigger combination.
- **Remaining limitation:** Arbitrary direct SQL can bypass the tracked quarantine workflow; the SQL console enables FK constraints so unsafe parent deletes fail, but it does not reconstruct a quarantine workflow for arbitrary statements. FK enforcement is connection-scoped and every new connection must explicitly enable it. Composite parent identities are rejected by current engine APIs.

### 7. Phase 6 Log Compaction Boundary
- **Status: Implemented for tested scope; Phase 6 is not signed off.** The sync API persists exact per-replica ACK vectors. Compaction requires the exact operation-ID intersection and dependency closure for every registered member; `HLC < min(T_ack)` is only a strict cutoff after that evidence.
- `data/checkpoint_store.sqlite` is the authoritative journal/manifest/payload archive. It uses SQLite rollback journaling and `synchronous=FULL`; snapshots are created with SQLite backup and stored under `data/checkpoint_snapshots/`. The store is provisioned only through `POST /api/v1/sync/checkpoint-store/initialize`. Startup never creates or repairs it automatically.
- Store validation checks SQLite integrity, schema/version, identity, manifest and operation-payload hashes, snapshot hashes, and snapshot integrity. Before ACK reconciliation or pruning, recovery requires exactly one snapshot per member and no unexpected entries; it checks replica ID/path/incarnation and membership epoch, validates an identity record embedded in each snapshot, recomputes user-schema and user-data fingerprints plus the exact log/receipt operation frontier, and compares those results with the manifest and the still-enrolled replica. It also verifies the manifest operation IDs and stable horizon against the committed ACK vectors. All acknowledged operation hashes must occur in every snapshot frontier. Missing, corrupt, swapped, duplicate, wrong-replica, wrong-schema, frontier-inconsistent, or otherwise unverifiable snapshots return `blocked` before ACK state or hot logs change. ACK reconciliation compares in-memory vectors with the atomically published registry, rolls back in-memory ACK mutation if registry save fails, and verifies durable state after each write. Existing unexpected registry membership is preserved and blocks recovery.
- Each replica transaction moves eligible operations to `_ss_compacted_receipts` and records the checkpoint marker atomically. A committed journal resumes after a crash; repeated recovery is idempotent. The manifest retains full operation payloads, while per-replica receipts retain identity and metadata. Snapshots preserve the materialized state at the captured frontier; the shared ancestor database is not rewritten.
- Missing/offline ACKs pin pruning. New replicas are copied from an enrolled materialized replica and begin without inherited ACKs. Creating a replica at an existing database path is refused. Automatic merge/replay of a returning replica’s uncheckpointed local tail is not implemented; keep the original database and resolve/reseed to a separate path after review. A stale replica whose checkpoint marker does not match is blocked from sync.
- Snapshot capture, tracked engine mutations, sync, conflict resolution, quarantine relinking, recovery, and direct compaction calls share a process-wide reentrant lock. This is single-process coordination only. The SQL console accepts writes but those writes are untracked, do not produce operation identities/quarantine records, and bypass this lock; they are unsupported for replica convergence. External processes can also bypass the lock. Registry JSON, checkpoint SQLite, snapshots, and replica SQLite files do not share a global transaction; manifest-driven roll-forward is tested, while ambiguous cross-store state fails closed.
- After a committed manifest, recovery accepts a hot-log tail only when tracked UPDATE/INSERT/DELETE operations replay from the validated snapshot in local sequence and reproduce the live user-data fingerprint. Tail operation IDs, sequence values, dependencies, row preconditions, triggers, and FK integrity are checked; snapshot identity/schema/frontier validation remains unchanged. RESOLVE, malformed tails, missing operation payloads, or untracked edits fail closed and retain hot logs; manual review is required. This is not general automatic offline-history merging.
- Recovery isolates checkpoint errors by checkpoint/database: a blocked checkpoint remains unchanged and is reported in `blocked_checkpoints`, while unrelated database checkpoints may proceed. Sync/compaction for the blocked checkpoint's own database still returns blocked. This is per-checkpoint isolation within one process, not multi-process coordination.
- The focused compaction suite passes 40 tests covering restart after post-manifest tracked UPDATE/INSERT/DELETE, malformed dependency/sequence/duplicate-ID/trigger-effect rejection with unchanged data, ACKs, logs, receipts, and checkpoint state, multi-replica ACK conflict preflight, registry-save failure after in-memory ACK mutation with same-process retry and restart, isolation of a blocked RESOLVE checkpoint from an unrelated valid checkpoint, failures between replica prune transactions, store/snapshot corruption, six snapshot-binding rejection cases, and direct-call/quarantine lock coverage. `synchronous=FULL` relies on SQLite and the local filesystem honoring flushes; true power-loss durability is not certified. The >70% result remains a row-count assertion for a 13-operation fixture, not a byte-size or workload-wide claim. Exact ACK maps can grow; arbitrary offline histories and general convergence are not guaranteed.

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
  - Alternative LWW sync orderings (e.g., sync starting from C or reversing the sequence).
  - SUM, AVG, or APPEND under 3-replica mesh topologies; BOUNDED_SUM has separate selected-schedule tests in §13.
  - Simultaneous concurrent mutations on all 3 replicas at the same physical time.
  - $N > 3$ replicas.
- Offline partition recovery and arbitrary N-replica histories remain unverified; Phase 3 only covers the finite schedules listed in §13.


### 11. Causality Not Distinguished in UPDATE vs DELETE (Documented — Phase 2 Adversarial Audit)

- The `ConflictDetector` uses a state-based snapshot diff, not a vector clock or explicit causal dependency log.
- When Replica A has an updated version of a row and Replica B has deleted it, the detector **always flags this as an `UPDATE_DELETE` conflict**, even if B's delete timestamp strictly dominates A's update timestamp (which would indicate B knew about A's change when it decided to delete).
- Distinguishing causally ordered deletions from concurrent ones requires tracking explicit causal dependencies (e.g., vector clocks, version vectors) between replicas — this is outside the current scope.
- **Timestamps ARE recorded** in the conflict record (`replica_a_ts`, `replica_b_ts`) and the `explanation` field includes the last known op type on the deleting replica, so human reviewers can inspect causal context when resolving.
- **Verified behavior:** Clean single-sided deletes (no mutation on the other replica) are **not** flagged as conflicts. `TestCausalityDocumented` documents this boundary.
- Explicit causal dependency tagging for general UPDATE/DELETE histories remains outside the implemented model; bounded signed deltas use stable operation identity and are handled separately in §13.

### 12. Operation Delivery Is Conservative and Pairwise (Phases 2.3–2.4)

- `sync_replicas(A, B)` replays logged INSERT, UPDATE, and DELETE operations in source-log order. A durable `origin_id`, `source_id`, and `source_sequence` identify operations across relay and restart; duplicate origins are ignored.
- The receiver checks origin identity, source sequence, single-column primary key, and expected row state inside one `BEGIN IMMEDIATE` transaction. Each row mutation and receipt-log entry commit together. Concurrent writes are serialized before validation.
- Locally changed receiver rows are preserved for conflict review. Repeated and relayed delivery is idempotent by origin identity.
- Relay occurs only during explicit pairwise sync; no background mesh delivery is provided.
- Delivery is conditional: an operation applies only if the receiver is absent/present as expected or matches the operation's logged prior value. Divergent/untracked rows stop replay and must be reviewed through three-way conflict detection. This is not a general convergence guarantee.
- UPDATE operations store scalar old/new values as text in the existing log format. Complex SQLite values, schema drift, non-deterministic triggers, and operation histories created outside tracked APIs are not fully supported for replay.
- Source sequence ordering is per originating replica. Concurrent histories from multiple sources are not globally ordered; the engine preserves divergence rather than choosing a winner.
- **Tracked-write requirement:** Safety depends on writes being recorded in `_ss_change_log` through the tracked engine/API paths. Direct SQL edits that bypass the change log cannot provide operation identity; row-snapshot comparison remains the only available safeguard for those edits.
- **Legacy ordering migration:** Existing change logs receive `sequence` values from their current SQLite rowids. The original ordering cannot be reconstructed if a legacy log was reordered or vacuumed before this migration.
- **Resolution relay:** Resolutions use a shared RESOLVE operation, source sequence, and dependencies on latest known row operations at both peers. A receiver checks expected snapshots. Missing prerequisites or unexpected state appear in `rejected_operations`; callers must review or retry them. Tests cover selected third-replica relay orders, not arbitrary histories.
- **Resurrection policy input:** `UPDATE_RESURRECTS` requires a dictionary row snapshot from conflict detection. Missing or malformed payloads are left flagged for review without write-back.
- **Replay failures:** An exception rolls back the current operation, while earlier operations in that sync may already have committed. Retrying deduplicates committed receipts by origin ID; the failed call can raise before returning its accumulated result.
- **INSERT validation:** Receiver checks the complete stored row after triggers before recording receipt. Ignored or mutating triggers are rejected and rolled back. Nondeterministic or external trigger side effects are not guaranteed.
- **Atomic conflict resolution:** The API and engine sync paths use one attached-database transaction for both replica files. WAL-mode databases are rejected because SQLite cannot guarantee the required cross-database atomic commit in that mode.

### 13. BOUNDED_SUM and N-Replica Phase 3 Boundary

- Configure a numeric column with the explicit policy string `BOUNDED_SUM[min=<number>,max=<number>]`. Bounds are finite and inclusive. Tracked writes validate the prior value and requested value, then store the signed delta, bound metadata, stable operation ID, and source sequence in the same local transaction.
- A received delta applies atomically only when the current value and resulting candidate are within bounds. Unsafe candidates are not clamped or receipted; they remain in the source log and appear in `rejected_operations` as pending. A later retry can apply them if preceding safe operations change the candidate.
- Bounded signed deltas on one cell are replayable out of source-sequence order and deduplicated by operation ID, but the receiver still rejects any delivery whose immediate candidate crosses a bound. A safe final mathematical sum alone does not guarantee every delivery order is safe.
- `test_n_replica_sync.py` verifies selected N=3/5 star, ring, and complete-pair schedules with reversed edge order, restart, and duplicate replay. These tests establish neither arbitrary-order nor general convergence. The guarantee demonstrated is bounded-value safety and receipt idempotency for the enumerated safe histories.
- Direct SQL and untracked writes bypass local bound validation and do not have durable delta identity. Replay detects an out-of-bound target and rejects the operation, but cannot reconstruct or certify the untracked history. Schema changes, nonnumeric SQLite storage, and externally mutating triggers remain outside the supported bounded-operation contract.
- The policy syntax is accepted by backend validation/API configuration; the current UI does not provide dedicated min/max bound controls. Configure bounds through the policy string until UI support is added.
