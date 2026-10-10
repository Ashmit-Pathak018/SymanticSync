# SemanticSync — System Architecture

**Version:** 1.0  
**Status:** Active

---

## 1. Architectural Principles

1. **Domain Agnosticism:** The semantic engine never references business concepts. It operates on normalized datatypes and registered policy names.
2. **Standard SQL:** Developers interact with SQLite using plain SQL. SemanticSync wraps conflict resolution, not query execution.
3. **Determinism:** All resolution functions are pure functions — same inputs, same outputs, always.
4. **Fail-Fast:** Incompatible policy configurations are rejected at validation time, never at runtime.
5. **Layered Separation:** CRDT convergence (replicas agree on a common state) is handled independently from Semantic Resolution (what that state should mean).

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                 SemanticSync Studio (Frontend)                  │
│  React 18 + Vite + Tailwind CSS                                │
│  Dashboard │ Schema+Policy │ SQL Console │ Conflicts │ Sync │  │
└───────────────────────────────┬────────────────────────────────┘
                                │ HTTP REST /api/v1
┌───────────────────────────────▼────────────────────────────────┐
│              SemanticSync API Server (FastAPI)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ DB Routes    │  │ Policy Routes│  │ Conflict/Sync Routes  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┴──────────────────────┘              │
│                           │                                      │
│              ┌────────────▼────────────┐                        │
│              │      AppState           │                        │
│              │  (In-memory + JSON)     │                        │
│              └────────────┬────────────┘                        │
│                           │                                      │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │                Semantic Engine Layer                       │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────┐   │  │
│  │  │ Schema Inspector │  │  Policy Registry + Validator  │   │  │
│  │  └──────────────────┘  └──────────────────────────────┘   │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────┐   │  │
│  │  │Conflict Detector │  │   Semantic Resolver           │   │  │
│  │  └──────────────────┘  └──────────────────────────────┘   │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────┐   │  │
│  │  │  Merge Manager   │  │   CRDTSyncEngine + HLC        │   │  │
│  │  └──────────────────┘  └──────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
     Replica A             Replica B             Replica C
    (SQLite .db)          (SQLite .db)          (SQLite .db)
```

---

## 3. Component Breakdown

### 3.1 Semantic Engine (`backend/engine/`)

The core, domain-agnostic conflict resolution and synchronization layer. No business logic lives here.

| Module | Responsibility |
|---|---|
| `schema_inspector.py` | SQLite `PRAGMA table_info` introspection; type affinity normalization |
| `policy_registry.py` | Registry of merge policies; `PolicyType` enum; compatibility definitions |
| `policy_validator.py` | Validates policy ↔ type pairings; returns `ValidationResult` |
| `semantic_resolver.py` | Deterministic conflict resolution per policy; returns `ResolutionResult` |
| `conflict_detector.py` | Three-way diff between base/replica_a/replica_b SQLite files |
| `merge_manager.py` | Conflict persistence (JSON); resolution tracking and write-back |
| `crdt_sync.py` | Hybrid Logical Clock (HLC); replica forking; full sync pipeline |

### 3.2 REST API (`backend/api/`)

FastAPI application serving all endpoints under `/api/v1`. Stateless per-request; relies on `AppState` singleton for persistence.

| Module | Routes |
|---|---|
| `routes_databases.py` | `GET/POST /databases`, `GET /databases/{id}/schema`, replicas |
| `routes_policies.py` | Policy CRUD, validation, registry |
| `routes_conflicts.py` | Detect, resolve, list, inspect conflicts |
| `routes_sync.py` | Status, run sync, generate controlled divergence |
| `routes_query.py` | SQL console against base or replica |
| `routes_benchmark.py` | Run benchmark, return SCR metrics |
| `routes_seed.py` | Seed demo workloads |
| `state.py` | `AppState` singleton — databases, replicas, policies, conflicts, metrics |

### 3.3 Benchmark Workloads (`backend/workloads/`)

Domain-specific data generators that produce ground-truth conflict scenarios for evaluation. They are the only place domain concepts appear.

### 3.4 Frontend (`frontend/`)

SemanticSync Studio — React 18 application consuming the REST API. See `docs/FRONTEND_ARCHITECTURE.md`.

---

## 4. Data Flow: Conflict Resolution

```
1. [Two replicas diverge]
   Replica A: quantity = 115   (was 100, +15)
   Replica B: quantity = 120   (was 100, +20)

2. [Conflict Detection]
   ConflictDetector.detect() → ConflictInfo {
     base_value: 100,
     replica_a_value: 115,
     replica_b_value: 120,
     policy: "SUM"
   }

3. [Policy Validation]
   PolicyValidator.validate("SUM", "INTEGER") → valid=True

4. [Semantic Resolution]
   SemanticResolver.resolve("SUM", 100, 115, 120)
   → resolved = 115 + 120 - 100 = 135
   → ResolutionResult { status: "resolved", resolved_value: 135 }

5. [Write-Back]
   UPDATE "products" SET "quantity" = 135 WHERE id = ?
   Applied to BOTH Replica A and Replica B

6. [Convergence]
   Replica A: quantity = 135 ✓
   Replica B: quantity = 135 ✓
```

---

## 5. Deployment Topology

SemanticSync is a **local-first, single-process** application in v1:

```
Developer Machine
├── python main.py          → FastAPI on :8000
├── npm run dev             → Vite dev server on :5173
└── data/                   → SQLite replicas on disk
```

There is no cloud component, no authentication, and no network requirement in v1.

---

## 6. Technology Choices

| Layer | Technology | Rationale |
|---|---|---|
| Backend Language | Python 3.10+ | Native `sqlite3` stdlib, clean type hints, fast prototyping |
| API Framework | FastAPI | Automatic OpenAPI docs, Pydantic v2 validation, async-ready |
| Database | SQLite 3 | Project target — stays within spec |
| Data Validation | Pydantic v2 | Type-safe request/response models |
| Frontend | React 18 + Vite | Fast HMR, modern ecosystem |
| Styling | Tailwind CSS | Utility-first, design token friendly |
| Testing | Pytest 9 | Robust parametrize, fixtures, fast |
