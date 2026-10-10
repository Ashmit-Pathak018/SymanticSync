# Changelog

All notable changes to the **SemanticSync** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-10-10

### Added
- Comprehensive project documentation suite (`docs/`):
  - `PRD.md`: Full product requirements, vision, user stories, and target benchmarks.
  - `ARCHITECTURE.md`: High-level system topology, layer separation, dataflow pipelines.
  - `CORE_WORKFLOW.md`: Step-by-step developer and runtime workflow documentation.
  - `DECISIONS.md`: Architecture Decision Records (ADR-001 through ADR-007).
  - `DATA_MODELS.md`: Dataclass and Pydantic schema specifications for all entities.
  - `SCHEMA_INSPECTION.md`: Introspection rules, SQLite type affinity mapping matrix.
  - `POLICY_SPECIFICATION.md`: Detailed semantics, commutativity, and formulas for all 7 policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`).
  - `CONFLICT_MODEL.md`: Formal three-way diff model, detection rules, and conflict lifecycle.
  - `SYNC_AND_CRDT.md`: Hybrid Logical Clock (HLC) and change log convergence protocols.
  - `API_SPECIFICATION.md`: Complete OpenAPI endpoint schemas and payload documentation.
  - `UX_SPECIFICATION.md`: View layouts and interaction design for SemanticSync Studio.
  - `DESIGN_SYSTEM.md`: Color tokens, typography, component standards.
  - `FRONTEND_ARCHITECTURE.md`: React 18, Vite, Tailwind CSS architectural plan.
  - `SQL_CONSOLE.md`: Interactive SQL console specification and security constraints.
  - `TESTING_STRATEGY.md`: Test classification, mock-free philosophy, and coverage goals.
  - `SECURITY.md`: SQL injection mitigation and local security boundaries.
  - `IMPLEMENTATION_PLAN.md`: Multiphase delivery roadmap.
  - `ROADMAP.md`: Short-, mid-, and long-term milestones.
  - `DEVELOPMENT_GUIDE.md`: Local setup, testing instructions, and CLI workflows.
  - `CODING_STANDARDS.md`: Engineering practices and static typing rules.
  - `CONTRIBUTING.md`: PR guidelines and collaboration rules.
  - `KNOWN_LIMITATIONS.md`: Constraints in v1 (single-PK, update divergence focus).
- Research documentation suite (`research/`):
  - Formal research problem formulation, literature review, baseline definitions, ground truths, evaluation metrics, results protocols, and publication plan.

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
