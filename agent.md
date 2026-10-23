# AGENT.MD — SemanticSync Agent Guidelines & Collaboration Contract

> **Notice to AI Agents & Collaborators:**  
> This file establishes strict guardrails, architecture principles, coding standards, and operational boundaries for all AI agents working on **SemanticSync**. Read this document carefully before creating or modifying any code. Do not deviate from these rules.

---

## 1. Project Mission & North-Star Principle

**SemanticSync** is a domain-independent developer tool and middleware layer for local-first relational databases.
- The underlying database engine is **standard SQLite**. Developers continue to use standard SQL.
- **Core Principle:** *"CRDT handles convergence; the semantic middleware handles the meaning of a conflict."*
- SemanticSync adds schema-level policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`) that define how conflicting changes across independent replicas are reconciled deterministically.
- **Domain Independence:** The engine **must never** hardcode domain concepts (e.g. what a "patient", "product", or "booking" is). It operates purely on column datatypes and explicitly configured merge policies.

---

## 2. Strict Rules of Engagement (Anti-Breakage Directives)

### Rule 1: Zero Destructive Actions Without Confirmation
- Never delete, overwrite, or truncate existing user database files, schemas, or git history without explicit approval.
- Any file modifications must be surgical, preserving existing comments, docstrings, and user implementations.

### Rule 2: Absolute Domain Independence in Core Engine
- The core engine (`backend/engine/`) must remain 100% agnostic to business domains.
- Policies are configured via schema metadata (e.g. `{ "table": "products", "column": "quantity", "policy": "SUM" }`).
- Never write `if table == 'patients': ...` inside the core resolver! Use registered, generic policy handlers.

### Rule 3: Fail Fast with Explicit Validation
- Schema and policy compatibility **must be validated before runtime execution**.
- Incompatible configurations (such as `AVG` on `TEXT` or `SUM` on `TEXT`) must fail immediately with HTTP `422 Unprocessable Entity` and a descriptive reason.
- Never silently swallow errors or coerce types insecurely.

### Rule 4: Determinism & Idempotency
- Conflict resolution algorithms must be **completely deterministic**:
  - Given identical replica values and base state, the resolver must produce identical output on all replicas.
  - Commutativity: `resolve(A, B) == resolve(B, A)` for symmetric policies like `SUM`, `AVG`.
  - Tie-breaking in `LWW`: must use deterministic ordering (e.g., Hybrid Logical Clock timestamp + Replica ID).

### Rule 5: Keep Standard SQL Standard
- Never introduce a proprietary query language. Queries must execute through standard SQLite connections (`sqlite3`).
- Parameterize all generated SQL operations to prevent SQL injection vulnerabilities.

### Rule 6: Respect the API Contract
- All internal REST endpoints must follow the `/api/v1` prefix and strictly honor the schemas defined in the Technical Architecture Document (TAD).
- Response models and HTTP status codes must match:
  - `400`: Malformed request
  - `404`: Entity not found
  - `409`: Conflict cannot be automatically resolved (requires manual review)
  - `422`: Policy incompatible with column datatype
  - `500`: Unexpected server error

### Rule 7: Adhere to UI Design Tokens
- SemanticSync Studio must adhere to the design system tokens:
  - **Primary**: `#315CFF`
  - **Navigation / Sidebar**: `#111A3A`
  - **Workspace Background**: `#F4F6FA`
  - **Panels & Borders**: `#D8DEEA`
  - **Success / Resolved**: `#2D9B62`
  - **Warning / Pending**: `#C98A1B`
  - **Danger / Conflict**: `#D94B5B`
- Do not rely on color alone for conflict status (always pair with plain text labels / badges).

---

## 3. Repository Architecture & Directory Boundaries

```text
SemanticSync/
├── agent.md                      # THIS FILE: Guardrails and agent instructions
├── README.md                     # Project overview and setup instructions
├── main.py                       # Unified runner (starts backend API & frontend)
│
├── backend/                      # Python backend (FastAPI + SQLite3 + CRDT)
│   ├── api/                      # REST API endpoints (/api/v1/...)
│   │   ├── routes_databases.py   # Workspaces, replicas, and schema inspection
│   │   ├── routes_policies.py    # Policy configuration and validation
│   │   ├── routes_conflicts.py   # Conflict detection and manual/auto resolution
│   │   ├── routes_sync.py        # Replica synchronization triggers and status
│   │   ├── routes_query.py       # SQL execution console
│   │   └── routes_benchmark.py   # Research evaluation metrics (SCR, latency, overhead)
│   ├── engine/                   # Domain-agnostic semantic core
│   │   ├── schema_inspector.py   # SQLite PRAGMA table/column introspection
│   │   ├── policy_registry.py    # Registry for SUM, AVG, APPEND, LWW, REJECT, MIN, MAX
│   │   ├── policy_validator.py   # Datatype compatibility verification
│   │   ├── conflict_detector.py  # Replica divergence detection
│   │   ├── semantic_resolver.py  # Deterministic merge policy execution
│   │   ├── merge_manager.py      # Result persistence & flagged conflict tracking
│   │   └── crdt_sync.py          # Replica change exchange & convergence protocol
│   ├── workloads/                # Benchmark workloads & ground truth datasets
│   │   ├── inventory_workload.py # Additive quantities, text notes, sku constraints
│   │   ├── notes_workload.py     # Document append, edit counters, author recency
│   │   └── health_workload.py    # Illustrative clinical benchmark (dosage AVG, notes APPEND, blood REJECT)
│   ├── tests/                    # Pytest test suite
│   │   ├── test_schema.py
│   │   ├── test_validation.py
│   │   ├── test_resolution.py
│   │   ├── test_sync.py
│   │   └── test_benchmark.py
│   └── requirements.txt
│
├── frontend/                     # SemanticSync Studio (React + Vite + Tailwind)
│   ├── src/
│   │   ├── components/           # Reusable UI widgets (badges, tables, cards, diffs)
│   │   ├── views/                # Studio screens
│   │   │   ├── Dashboard.jsx     # Workspace summary, activity feed, conflict preview
│   │   │   ├── Databases.jsx     # Database workspaces & replica manager
│   │   │   ├── SchemaEditor.jsx  # Schema & semantic policy designer with live validation
│   │   │   ├── SqlConsole.jsx    # SQLite query runner with Run / Explain / Format
│   │   │   ├── Conflicts.jsx     # Conflict inspector & manual resolution modal
│   │   │   ├── SyncHub.jsx       # Replica topology, controlled conflict generator & sync runner
│   │   │   ├── Analytics.jsx     # Research benchmark comparisons (Baseline vs SemanticSync)
│   │   │   └── Settings.jsx      # Telemetry, documentation, and policy definitions
│   │   ├── services/api.js       # Typed API client
│   │   └── styles/               # Theme tokens & Tailwind config
│   ├── package.json
│   └── vite.config.js
│
└── data/                         # Local database replicas storage (.db files)
    └── .gitkeep
```

---

## 4. Policy Registry Specification

| Policy | Compatible Datatypes | Merge Behavior | Typical Use Case |
|---|---|---|---|
| **`SUM`** | `INTEGER`, `REAL` | Computes additive delta ($base + \Delta A + \Delta B$) or additive total | Inventory stock, counters, balances |
| **`AVG`** | `INTEGER`, `REAL` | Arithmetic mean of values ($(A + B) / 2.0$) | Sensor readings, ratings, dosages |
| **`APPEND`** | `TEXT` | Concatenates divergent entries (`A; B` or with newline) | Notes, log entries, tags |
| **`LWW`** | Any type | Selects value with highest logical timestamp / HLC | Profile fields, status where recency governs |
| **`REJECT`**| Any type | Flags record for manual review; leaves state unmerged | Critical keys, clinical blood type, conflicting statuses |
| **`MIN`/`MAX`**| `INTEGER`, `REAL` | Deterministic lower/upper bound | Pricing limits, operational thresholds |

---

## 5. Verification Checklist for Agents

Before concluding any implementation task, an agent **must verify**:
- [ ] Schema inspection works dynamically on any SQLite `.db` file via standard PRAGMAs.
- [ ] Incompatible policies are rejected before runtime (`test_validation.py` passes).
- [ ] Deterministic resolution passes for `SUM`, `AVG`, `APPEND`, `LWW`, and `REJECT`.
- [ ] Multi-replica sync cleanly converges divergent local database files.
- [ ] Benchmark runner reports **SCR (Semantic Correctness Rate)** using the workload's conflict denominator, identifies any narrow row-agreement metric as such, and separates measured batch-sync delta from resolver-only overhead. Do not claim full-database convergence unless complete database state is compared.
- [ ] All API endpoints respond according to the specification.
- [ ] The frontend compiles without lint/type errors and communicates with the backend.

---

## 6. Prohibited Agent Behaviors
❌ **DO NOT** wipe or replace user databases without asking.  
❌ **DO NOT** hardcode domain logic into `backend/engine/`.  
❌ **DO NOT** install massive unrequested external dependencies without checking package availability.  
❌ **DO NOT** remove unit tests to make builds pass.  
❌ **DO NOT** mock out core sync algorithms with fake timeouts when real SQLite operations are required.
