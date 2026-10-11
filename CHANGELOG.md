# Changelog

All notable changes to the **SemanticSync** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
