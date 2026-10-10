# SemanticSync — Product Requirements Document (PRD)

**Version:** 1.0  
**Status:** Active  
**Authors:** SemanticSync Core Team  
**Last Updated:** October 2026

---

## 1. Problem Statement

Distributed, offline-first, and collaborative applications built on SQLite face a fundamental unsolved challenge: when independent replicas of the same database diverge due to concurrent writes, how should conflicting field values be reconciled?

Generic CRDT frameworks (Last-Write-Wins, Add-Wins Sets, etc.) solve the **convergence** problem — they ensure all replicas eventually reach the same state — but they do not solve the **semantic** problem. A Last-Write-Wins strategy applied to a `quantity` column in an inventory system loses stock updates. A LWW strategy applied to a `clinical_notes` column silently discards a clinician's observation.

**SemanticSync solves this.** It provides a **schema-level semantic policy middleware** layer that sits above CRDT convergence mechanics and determines *how* a conflict should be resolved based on what the field *means* in its domain context.

---

## 2. Vision

> *"Developers should be able to declare the meaning of their data fields at schema time, and let the synchronization layer honor that meaning during conflict resolution — without writing custom merge logic for every field."*

SemanticSync allows developers to annotate their existing SQLite schemas with semantic policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`) and immediately gain semantically correct conflict resolution — while keeping their existing SQL toolchain unchanged.

---

## 3. Goals

| Goal | Priority |
|---|---|
| Provide schema-level semantic conflict resolution for SQLite | P0 |
| Remain domain-agnostic in the engine layer | P0 |
| Integrate with existing SQLite databases without schema migration | P0 |
| Provide a developer workspace (SemanticSync Studio) for policy design | P1 |
| Quantifiably demonstrate superiority over Generic LWW baseline via benchmark | P1 |
| Support multi-replica (3+) synchronization scenarios | P1 |
| Provide a SQL Console for replica state inspection | P2 |

## 4. Non-Goals

- SemanticSync is **not** a general-purpose distributed database.
- SemanticSync does **not** replace application-level business logic.
- SemanticSync does **not** support non-SQLite databases in v1.
- SemanticSync is **not** a cloud sync service — it operates locally.

---

## 5. Target Users

### Primary: Research / Academic
- Distributed systems researchers studying conflict-free data structures, CRDT semantics, and local-first software patterns.
- Graduate students implementing and evaluating sync middleware.

### Secondary: Developer Tools
- Developers building offline-first, local-first, or edge-computing applications on SQLite.
- Teams building collaborative desktop or mobile applications with shared data.

---

## 6. User Stories

### Core Engine
- As a developer, I want to annotate my SQLite columns with semantic policies so that concurrent writes are reconciled according to domain meaning rather than arbitrary timestamp ordering.
- As a developer, I want the engine to reject invalid policy assignments (e.g. `AVG` on a `TEXT` column) before runtime so I cannot misconfigure my schema.
- As a developer, I want conflict resolution to be deterministic so that all replicas always converge to the same value given the same input.

### Studio UI
- As a developer, I want to browse my SQLite schema and assign policies column-by-column with visual validation feedback.
- As a developer, I want to run SQL queries directly against any replica to inspect its state.
- As a developer, I want to simulate a conflict by injecting divergent values into two replicas and watch the policy resolve it.
- As a researcher, I want to run a benchmark comparing Generic LWW vs. SemanticSync across three domain workloads and see the Semantic Correctness Rate (SCR) for each.

---

## 7. Requirements

### Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Engine must support policies: `SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX` |
| FR-02 | Each policy must be validated for type compatibility before being applied |
| FR-03 | `SUM` must implement additive delta reconciliation: `resolved = a + b - base` |
| FR-04 | `AVG` must return exact arithmetic mean: `(a + b) / 2.0` |
| FR-05 | `APPEND` must concatenate both values deterministically (ordered by replica_id) |
| FR-06 | `LWW` must use Hybrid Logical Clock for ordering; deterministic tie-break via replica_id |
| FR-07 | `REJECT` must flag conflict for manual review without mutating any replica |
| FR-08 | All SQL operations must use parameterized queries (no string interpolation) |
| FR-09 | Schema inspection must work via standard SQLite `PRAGMA table_info` |
| FR-10 | API must return `HTTP 422` for invalid policy/type combinations |
| FR-11 | Studio must display schema, policies, conflicts, and sync results |
| FR-12 | Benchmark harness must produce Semantic Correctness Rate (SCR) metric |
| FR-13 | System must support seeding 3 demo workloads: Inventory, Notes, Healthcare |

### Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | Policy resolution must be deterministic: same inputs always produce same output |
| NFR-02 | Engine layer must contain zero domain-specific logic |
| NFR-03 | API must start within 5 seconds |
| NFR-04 | All tests must pass in < 5 seconds |
| NFR-05 | No external cloud dependencies; operates fully offline |
| NFR-06 | Python 3.10+ and Node.js 18+ compatibility |

---

## 8. Success Criteria

- **All 56+ automated tests passing** across schema inspection, policy validation, semantic resolution, sync convergence, and API contract.
- **Semantic Correctness Rate (SCR) ≥ 90%** on benchmark workloads for SemanticSync vs ~33% for Generic LWW baseline.
- **Zero domain logic in `backend/engine/`** — verified by code review.
- **Swagger UI operational** at `/docs` for all API endpoints.
- **SemanticSync Studio builds** and connects to the backend API.
