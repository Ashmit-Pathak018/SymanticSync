# SemanticSync 🔄

> **A developer workspace for designing, querying, and synchronizing local-first relational databases with schema-level semantic merge policies.**

---

## 💡 Core Philosophy
- **Keep SQL and SQLite:** The underlying database remains ordinary SQLite and developers continue to use standard SQL for creating tables, querying, and updating records.
- **Build Principle:** *CRDT handles convergence; the semantic middleware handles the meaning of a conflict.*
- **Domain Independence:** The engine operates on datatypes and schema configuration (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`), never hardcoding domain assumptions.

---

## 🚀 Key Features
- **Schema-Level Semantic Policies:**
  - `SUM`: Additive delta reconciliation for numeric columns (e.g. inventory counts, balances).
  - `AVG`: Arithmetic mean calculation (e.g. sensor readings, dosages, ratings).
  - `APPEND`: Preserves concurrent text contributions with deterministic ordering.
  - `LWW`: Last-Write-Wins based on Hybrid Logical Clock (HLC) timestamps and replica IDs.
  - `REJECT`: Flags ambiguous or critical divergences for human review (e.g. blood types, statuses).
  - `MIN` / `MAX`: Extremum bounding.
- **Fail-Fast Policy Compatibility Validation:** Incompatible configurations (such as `AVG` on `TEXT`) are caught before runtime (`HTTP 422`).
- **Dynamic SQLite Schema Inspector:** Automatically inspects tables, column datatypes, and constraints using SQLite `PRAGMA` introspection.
- **CRDT Synchronization Engine:** Multi-replica change tracking using Hybrid Logical Clocks (HLC) and three-way conflict detection.
- **Research Benchmark Suite:** Empirical measurement comparing Generic Baseline (LWW) vs SemanticSync middleware across three domain workloads (Inventory, Notes, Healthcare) measuring **Semantic Correctness Rate (SCR)**, **Convergence**, and **Overhead**.
- **REST API (`/api/v1`):** Complete REST API for workspaces, schemas, policies, conflict resolution, synchronization, and SQL console.

---

## 📁 Project Structure

```text
SemanticSync/
├── agent.md                      # AI agent guardrails and collaboration contract
├── README.md                     # Project overview and documentation
├── main.py                       # API server runner
│
├── backend/                      # Python backend (FastAPI + SQLite3 + CRDT)
│   ├── api/                      # REST API endpoints (/api/v1/...)
│   │   ├── models.py             # Pydantic v2 schemas
│   │   ├── state.py              # Persistent AppState store
│   │   ├── routes_databases.py   # Workspace and replica management
│   │   ├── routes_policies.py    # Schema policies and validation
│   │   ├── routes_conflicts.py   # Conflict detection and resolution
│   │   ├── routes_sync.py        # Synchronization pipeline
│   │   ├── routes_query.py       # SQL console execution
│   │   ├── routes_benchmark.py   # Research evaluation metrics (SCR, latency)
│   │   └── routes_seed.py        # Demo workload seeders
│   ├── engine/                   # Domain-agnostic semantic core
│   │   ├── schema_inspector.py   # SQLite PRAGMA introspection
│   │   ├── policy_registry.py    # Registry for SUM, AVG, APPEND, LWW, REJECT, etc.
│   │   ├── policy_validator.py   # Type compatibility verification
│   │   ├── conflict_detector.py  # Three-way replica divergence detection
│   │   ├── semantic_resolver.py  # Deterministic merge policy execution
│   │   ├── merge_manager.py      # Result persistence & review tracking
│   │   └── crdt_sync.py          # HLC & multi-replica sync engine
│   ├── workloads/                # Benchmark workloads & ground-truth datasets
│   │   ├── base_workload.py      # Abstract base workload template
│   │   ├── inventory_workload.py # Stock counts, descriptions, SKU policies
│   │   ├── notes_workload.py     # Document collaboration and author tracking
│   │   └── health_workload.py    # Illustrative healthcare benchmark
│   ├── tests/                    # Pytest test suite (56 automated tests)
│   │   ├── test_schema.py
│   │   ├── test_validation.py
│   │   ├── test_resolution.py
│   │   ├── test_sync.py
│   │   ├── test_benchmark.py
│   │   └── test_api.py
│   └── requirements.txt
│
├── frontend/                     # SemanticSync Studio (React 19 + Vite + Tailwind CSS)
│   ├── src/
│   │   ├── components/           # UI badges, buttons, cards, modals, layout
│   │   ├── context/              # Global AppContext state management
│   │   ├── services/api.js       # Centralized REST API service
│   │   ├── views/                # Studio views (Dashboard, Schema, SQL, Conflicts, Sync, Benchmark)
│   │   ├── App.jsx               # React Router configuration
│   │   └── main.jsx              # React app entry point
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
│
└── data/                         # Local database storage (.db SQLite files)
```

---

## 🛠️ Getting Started

### 1. Install Backend Dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### 3. Run Automated Tests
```bash
pytest backend/tests/ -v
```

### 4. Start the Application

You can start both the backend API and the frontend Studio simultaneously using the unified runner, or start them in separate terminals:

**Option A — Unified Runner (Starts both Backend & Frontend):**
```bash
python main.py --with-frontend
```

**Option B — Independent Processes:**
- **Terminal 1 (Backend API):**
  ```bash
  python main.py
  ```
  - API Server: `http://127.0.0.1:8000`
  - Swagger Documentation: `http://127.0.0.1:8000/docs`

- **Terminal 2 (Frontend Studio):**
  ```bash
  cd frontend
  npm run dev
  ```
  - Studio UI: `http://localhost:5173`
  - All API calls (`/api/...`) are automatically proxied to `http://127.0.0.1:8000`.

---

## 📜 REST API Contract Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/databases` | List registered databases |
| `POST` | `/api/v1/databases` | Register a database |
| `GET` | `/api/v1/databases/{id}/schema` | Inspect schema metadata |
| `GET` | `/api/v1/databases/{id}/policies` | Return assigned semantic policies |
| `PUT` | `/api/v1/databases/{id}/policies` | Batch update policy assignments |
| `POST` | `/api/v1/validate-policy` | Validate policy against column datatype |
| `POST` | `/api/v1/conflicts/detect` | Detect divergences across replicas |
| `POST` | `/api/v1/conflicts/resolve` | Resolve conflict (auto / pick_a / pick_b / custom) |
| `GET` | `/api/v1/conflicts` | List detected/pending conflicts |
| `GET` | `/api/v1/sync/status` | Return synchronization status |
| `POST` | `/api/v1/sync/run` | Execute synchronization pipeline |
| `POST` | `/api/v1/query` | Execute SQLite SQL queries |
| `POST` | `/api/v1/benchmark/run` | Run empirical benchmark comparison |
| `GET` | `/api/v1/metrics` | Return benchmark evaluation metrics |
| `POST` | `/api/v1/seed` | Seed demo workloads |
