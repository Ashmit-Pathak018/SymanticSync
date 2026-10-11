# Changelog

All notable changes to the **SemanticSync** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
