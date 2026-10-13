# Changelog

All notable changes to the **SemanticSync** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Phase 4/6 Remediation

### Changed
- Replaced resolver-only benchmark figures with actual tracked writes and two-replica synchronization under identical seeded LWW/SUM traces. SCR, VRA, CR, write latency percentiles, sync-time delta, and log sizes are derived from executed rows/logs; JSON retains raw operations and final states, CSV includes numeric metrics and operation latencies.
- Enabled SQLite FK constraints before relevant write transactions; added nested atomic quarantine, correct referenced-column/composite FK discovery, received-write rejection, and verified child restoration before relink status changes.
- Removed repeated change-log backfills from received-operation replay and paired conflict resolution; indexed stable operation receipt lookups and avoided repeated receiver schema checks. Added a legacy log-upgrade regression.
- Receiver replay now commits once per source batch while keeping a rollback savepoint per operation; a failed operation is isolated, and an unexpected failure rolls back the batch for safe retry. The same-seed 5,000-operation/20% case improved from 62.52 to 16.097 seconds; two same-seed repeats measured 15.817 and 15.915 seconds. The 30-second gate passes reproducibly.
- Phase 4 and Phase 5 are verified for their documented tested scopes; no general convergence or production-capacity claim is made.

### Verification
- Historical Phase 4/5 gate: focused replay/FK/bounded/N-replica suites **92 passed**, full backend suite **241 passed**, one existing Starlette/httpx deprecation warning. All nine optimized runs and three repeated gate runs are exported to `.codex-phase4-optimized-matrix-20261013/`.
- Historical Phase 6 partial implementation: compaction suite **12 passed**; full backend suite **253 passed**, one existing Starlette/httpx deprecation warning; `git diff --check` passed. This earlier result covered selected ACK, replay, restart, boundary, bootstrap, and rollback schedules.
- Added an explicitly initialized, FULL-synchronous SQLite checkpoint store with immutable manifests, full operation payload archives, hashed SQLite snapshots, fail-closed integrity/identity validation, and restartable journal recovery. A registry ACK gap is reconciled only from a validated committed manifest; ambiguous membership, missing/corrupt store or snapshot, and mismatched operation history block pruning.
- Added one process-wide reentrant lock for tracked mutations, sync, conflict resolution, replica creation, checkpoint capture, and pruning. Replica creation refuses to overwrite an existing path, preserving an offline replica and its uncheckpointed local operations.
- Latest Phase 6 verification: focused compaction/recovery suite **21 passed**; full backend suite **262 passed**, one existing Starlette/httpx deprecation warning. Phase 6 remains unsigned pending review. Automatic offline-tail merge, multi-process coordination, and power-loss guarantees remain unsupported.

## [0.3.5] - 2026-10-12

### Added — Phase 3 Bounded Operations and Mesh Validation
- Added explicit `BOUNDED_SUM[min=...,max=...]` policy parsing, finite inclusive bounds, and signed-delta operation metadata.
- Tracked writes reject out-of-bound values. Unsafe received deltas remain pending and visible to callers; they are never clamped or silently receipted. Same-source reordered deltas are deduplicated by stable operation identity.
- Added focused bounded-operation and N=3/5 star, ring, and complete-pair schedule tests. These verify the enumerated safe schedules, not general convergence.
- Phase 3.1 hardening verifies bounded local writes after triggers, rolls back ignored or altered writes before receipt logging, and preserves integer bounds exactly above $2^{53}$ in SQLite numeric metadata.
- Pending/restart regressions now compare each original operation ID, source ID, source sequence, and exactly one receipt on every replica.
- Verification: focused suites **28 passed**; full backend suite **181 passed**, one existing Starlette/httpx deprecation warning; `git diff --check` passed.

## [0.3.4] - 2026-10-12

### Fixed — Phase 2.4 Integrity
- Receiver INSERT replay validates the complete stored row before atomically recording receipt; ignored or row-mutating triggers reject and roll back the operation.
- Conflict resolutions use a shared RESOLVE payload, stable resolution source sequence, and explicit row-operation dependencies so either peer can relay the resolution to a third replica. Rejected operations are returned in sync results.
- UPDATE_RESURRECTS now flags missing or non-row payloads unresolved without writing or reporting success; relay regressions assert third-replica metadata and exactly one receipt after duplicate relay.
- Added retry-after-partial-failure and resolution relay regressions. Latest verification: focused suites 47 passed; full backend suite 129 passed with one existing Starlette/httpx deprecation warning; frontend production build succeeded; `git diff --check` passed.
- These selected schedules do not establish general convergence; see `KNOWN_LIMITATIONS.md` §12.

### Phase 1/2 Closeout Evidence
- Added `test_adversarial_resolution.py` with reproducible generated policy properties, APPEND boundaries, invalid-input rollback, and immediate-lock checks. Added row-mutation conflict persistence/recovery coverage.
- At that closeout point, the full backend suite had 143 passing tests and one existing Starlette/httpx deprecation warning. The INSERT-collision acceptance was still open then; no Phase 3 work was included.

### Approved Phase 2 INSERT-Collision Resolution
- PK and secondary-UNIQUE collisions retain both complete row payloads in durable reviewable conflicts. Reviewers can select either payload or provide a complete replacement.
- Two-replica changes and stable resolution receipts are written in one transaction. Stale/missing participant rows, UNIQUE violations, and failed writes do not report success; registry persistence uses atomic replacement, and retries deduplicate committed resolution receipts.
- Focused INSERT-collision, integrity, and mutation-conflict suites: 58 passed. Full backend suite: 153 passed with one existing Starlette/httpx deprecation warning; `git diff --check` passed.
- Automatic LWW/re-key and third-replica relay of INSERT-collision resolutions remain unsupported. This evidence does not establish general convergence.

### Added — Phase 2.3 Operation Propagation
- Logged INSERT, UPDATE, and DELETE operations replay conditionally in source order, carrying stable origin identity and source sequence through pairwise relays and restart.
- Divergent rows stop replay so local edits are retained for conflict review; this is conservative pairwise propagation, not a general convergence guarantee.
- Added regressions for three-replica relay, reversed pair direction, duplicate delivery, delayed stale deletes, delete/reinsert, restart, and concurrent local edits. Verification: 120 backend tests passed (one existing Starlette/httpx deprecation warning); frontend production build succeeded.
- Unsupported cases and replay preconditions are documented in `KNOWN_LIMITATIONS.md` §12.

---

## [0.3.2] - 2026-10-12

### Fixed — Phase 2.1 Hardening
- **Durable stale-delete delivery:** `sync_replicas()` propagates DELETE records to unchanged replicas when their row contents match the tombstone snapshot. Any explicit local row operation blocks automatic deletion and leaves the case to conflict review. Receiving replicas record their own tombstones, allowing later pairwise relay; duplicate delivery is idempotent.
- **Conflict resolution failures are visible:** `/conflicts/resolve` no longer swallows replica write errors. It returns a clear HTTP error, and composite-PK tables are rejected instead of being treated as single-PK tables.
- **Conflict detection API:** Correctly consumes `DetectResult` and reports skipped table names in `X-SemanticSync-Skipped-Tables` while preserving the list response shape.
- **Regression coverage:** Added stale, delayed, and duplicate tombstone delivery checks.

---

## [0.3.3] - 2026-10-12

### Fixed — Phase 2.2 Integrity
- **Superseded tombstones:** Delivery now considers the latest durable per-row operation. A later INSERT or UPDATE prevents replay of an older DELETE. Tombstone origin identity is preserved through multi-hop relay.
- **Atomic tombstone delivery:** Receiver validation, conditional deletion, and durable log insertion occur in one `BEGIN IMMEDIATE` transaction. A migrated explicit sequence column preserves append order across restarts and vacuum operations.
- **Composite primary keys:** The sync engine rejects composite keys in direct mutation and tombstone paths; it never addresses them through the first key column.
- **Atomic conflict resolution:** API and engine sync paths update both replicas in one attached-database transaction and record the shared operation identity. Row-level `None` means delete; cell-level `None` means SQL NULL. Missing rows and write failures roll back and leave conflicts unresolved.
- **Unsupported table visibility:** Sync responses now include `skipped_tables`, and SyncHub displays a warning.
- **Regression tests:** Added 16 reinsert, relay/restart, reverse-relay, identity deduplication, atomicity/race, composite-PK, delete/NULL, missing-row, ignored-delete, WAL rejection, rollback, and API response tests. Current full backend suite: **117 passed** (one existing deprecation warning).

---

## [0.3.1] - 2026-10-11

### Fixed — Phase 2 Adversarial Audit
- **`conflict_detector.py` — Composite-PK PRAGMA Bug:** `_get_pk_column` used `pk == 1` to find PK columns. SQLite PRAGMA assigns `pk=1` for the first PK column and `pk=2, 3, ...` for subsequent columns in composite PKs. Fixed to use `pk > 0` and return `None` when more than one PK column is found. Composite-PK tables were previously silently mislabeled as single-PK tables.
- **`conflict_detector.py` — Skipped Tables Now Surfaced:** `detect()` now returns `DetectResult(conflicts, skipped_tables)` (a `NamedTuple`). Tables with composite or absent PKs appear in `skipped_tables` rather than being silently dropped with no caller-visible signal.
- **`crdt_sync.py` — `DELETE_WINS` Silent Error Swallowing:** Previously `except Exception: pass` was used for both `apply_delete` calls and `auto_resolved` was incremented unconditionally. Fixed: only `RuntimeError("…not found…")` is suppressed (idempotent). Other failures move the conflict to `flagged_conflicts`. `auto_resolved` is incremented only after both deletes succeed.
- **`crdt_sync.py` — `SyncResult.skipped_tables`:** Added `skipped_tables: list[str]` field to `SyncResult` so callers of `sync_replicas()` can observe which tables were skipped.

### Added — Phase 2 Adversarial Audit
- **`_get_row_update_ts()` helper (`conflict_detector.py`):** Correctly retrieves UPDATE timestamps by scanning actual column-level keys (not `"*"`), since `apply_change` writes `column_name = <actual_col>`. Used in Cases 3 & 4 to populate accurate timestamps in conflict records.
- **8 adversarial regression tests (`test_mutation_conflicts.py`):** `TestCausalityDocumented` (3 tests), `TestCompositePKSurfaced` (3 tests), `TestStaleTombstonePropagation` (2 tests). Total test count: **100 passing**.

### Documented — Phase 2 Adversarial Audit
- **`KNOWN_LIMITATIONS.md` §11:** Causality not distinguished in UPDATE vs DELETE — state-based diffing only; timestamps informational.
- **`KNOWN_LIMITATIONS.md` §12:** Stale replica tombstone propagation gap — unmodified stale replicas require explicit pairwise sync.

---

## [0.3.0] - 2026-10-11


### Added — Phase 2: Full Row-Mutation Conflict Model
- **Row-Mutation Conflict Taxonomy (`backend/engine/conflict_detector.py`):**
  - Full relational mutation lifecycle: `INSERT vs INSERT` (PK & UNIQUE collisions), `UPDATE vs DELETE` (concurrent & tombstone), `DELETE vs DELETE` (idempotent agreement).
  - Extended `ConflictInfo` dataclass with `conflict_type`, `status`, `resolution_mode`, `resolved_value`, and `explanation`.
  - Secondary UNIQUE constraint/index collision discovery via SQLite PRAGMA inspection.
  - Distinct handling for identical duplicate delivery (zero false conflicts).
- **CRDT Sync Engine Row Mutations (`backend/engine/crdt_sync.py`):**
  - Added `apply_insert()` and `apply_delete()` methods for tracked row-level operations with explicit `op_type` in `_ss_change_log`.
  - Configurable tombstone policy resolution: `FLAG_FOR_REVIEW` (default safety stop), `DELETE_WINS`, and `UPDATE_RESURRECTS`.
- **API & State Layer Integration (`backend/api/`):**
  - Updated Pydantic schemas in `models.py` with `tombstone_policy` and `conflict_type`.
  - Updated `routes_conflicts.py` and `routes_sync.py` to preserve row-level payloads and execute row-level manual/auto resolutions.
- **Automated Test Suite (`backend/tests/test_mutation_conflicts.py`):**
  - 10 comprehensive tests verifying each supported mutation class: PK collisions, UNIQUE collisions, identical delivery idempotency, UPDATE vs DELETE default review and policies, 3-replica DELETE convergence, repeat sync idempotency, and audit trails.
  - Total test count expanded to 92 passing tests.

---

## [0.2.1] - 2026-10-10

### Added
- **Frontend Studio Integration (PR #1):**
  - Full React 18, Vite, and Tailwind CSS web application in `frontend/`.
  - Seven primary interactive views: Dashboard, Databases, SchemaEditor, Conflicts, SyncHub, SqlConsole, Analytics, and Settings.
  - Integration with backend REST API under `/api/v1`.
  - Unified runner in `main.py` supporting concurrent API and UI execution (`--with-frontend`).

### Documentation & Scientific Reconciliation
- Reconciled complete project documentation across `docs/` and `research/`:
  - Established formal algebraic classifications for all 7 merge policies (`POLICY_SPECIFICATION.md`).
  - Added full row-mutation conflict taxonomy covering `INSERT` collisions, `UPDATE vs DELETE` tombstones, and foreign-key orphan quarantine (`CONFLICT_MODEL.md`).
  - Formalized causal stability log compaction and multi-replica convergence constraints (`SYNC_AND_CRDT.md`).
  - Documented explicit requirement-to-test traceability matrix (`docs/TRACEABILITY_MATRIX.md`).
  - Produced empirical audit report distinguishing verified codebase facts from planned extensions (`docs/AUDIT_REPORT.md`).

---

## [0.2.0] - 2026-10-10

### Added
- Initial project documentation suite (`docs/`) and research specifications (`research/`).

---

## [0.1.0] - 2026-10-10

### Added
- Core backend engine (`backend/engine/`):
  - `SchemaInspector`: SQLite PRAGMA inspection and canonical type normalization (`INTEGER`, `REAL`, `TEXT`, `BLOB`, `NUMERIC`).
  - `PolicyRegistry`: Policy definitions, enum type mappings, and validation registry.
  - `PolicyValidator`: Fail-fast type compatibility verification with descriptive errors.
  - `SemanticResolver`: Deterministic resolution for `SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`.
  - `ConflictDetector`: Three-way diff algorithm for concurrent divergence detection.
  - `MergeManager`: Persistent conflict registry and resolution history.
  - `CRDTSyncEngine`: Hybrid Logical Clock (HLC), replica lifecycle, and full synchronization pipeline.
- REST API layer (`backend/api/`):
  - FastAPI application serving under `/api/v1`.
  - Endpoints for databases, schemas, replicas, policies, conflicts, sync, SQL queries, benchmarks, and seeding.
  - In-memory and JSON-backed `AppState` management.
- Evaluation workloads (`backend/workloads/`):
  - `InventoryWorkload`, `NotesWorkload`, and `HealthWorkload` test scenarios with ground-truth conflict pairs.
- Automated Test Suite (`backend/tests/`):
  - 56 passing pytest tests covering schema inspection, policy validation, deterministic resolution, CRDT synchronization, and API contracts.
