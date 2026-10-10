# SemanticSync — Development Guide

**Version:** 1.0

---

## Prerequisites

| Tool | Minimum Version | Check |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 8+ | `npm --version` |
| Git | 2.30+ | `git --version` |

> Windows users: Use PowerShell. WSL2 is also supported.

---

## Backend Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Ashmit-Pathak018/SymanticSync.git
cd SemanticSync
```

### 2. Create a Virtual Environment (Recommended)
```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS/Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

**Contents of `backend/requirements.txt`:**
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
python-multipart>=0.0.9
pytest>=8.0.0
```

### 4. Create the Data Directory
The `data/` directory must exist before running the server:
```bash
# It should already exist (tracked via data/.gitkeep)
ls data/   # Should see .gitkeep
```

### 5. Run the API Server
```bash
python main.py
# OR
uvicorn backend.app:app --reload --port 8000
```

API will be available at:
- **REST API:** `http://127.0.0.1:8000/api/v1`
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

---

## Running Tests

```bash
# Run all tests
python -m pytest backend/tests/ -v

# Run tests with short tracebacks
python -m pytest backend/tests/ -v --tb=short

# Run specific test file
python -m pytest backend/tests/test_resolution.py -v

# Run tests matching name pattern
python -m pytest backend/tests/ -k "test_sum" -v

# Run with stdout output visible
python -m pytest backend/tests/ -v -s
```

**Expected output:** `56 passed, 0 failed`

---

## Seeding Demo Data

The fastest way to get data into the system:

```bash
# Start the server first
python main.py &

# Seed all workloads
curl -X POST http://127.0.0.1:8000/api/v1/seed \
  -H "Content-Type: application/json" \
  -d '{"workload": "all"}'
```

Or from the Studio: click **Seed Demo Data** in the Dashboard.

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:5173`. Proxies `/api` requests to `http://127.0.0.1:8000`.

---

## Project Structure

```
SemanticSync/
├── main.py                    ← Uvicorn runner
├── agent.md                   ← AI collaboration contract
├── README.md
├── CHANGELOG.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── app.py                 ← FastAPI app + routers
│   ├── engine/                ← Core conflict resolution engine
│   │   ├── schema_inspector.py
│   │   ├── policy_registry.py
│   │   ├── policy_validator.py
│   │   ├── semantic_resolver.py
│   │   ├── conflict_detector.py
│   │   ├── merge_manager.py
│   │   └── crdt_sync.py
│   ├── api/                   ← REST API routes + state
│   │   ├── state.py
│   │   ├── models.py
│   │   ├── routes_databases.py
│   │   ├── routes_policies.py
│   │   ├── routes_conflicts.py
│   │   ├── routes_sync.py
│   │   ├── routes_query.py
│   │   ├── routes_benchmark.py
│   │   └── routes_seed.py
│   ├── workloads/             ← Demo data generators
│   │   ├── base_workload.py
│   │   ├── inventory_workload.py
│   │   ├── notes_workload.py
│   │   └── health_workload.py
│   └── tests/                 ← Pytest test suite
├── frontend/                  ← React + Vite + Tailwind
├── docs/                      ← Documentation
├── research/                  ← Research materials
└── data/                      ← Runtime SQLite files (gitignored)
    └── .gitkeep
```

---

## Common Development Tasks

### Add a New Policy
1. Add `NEW_POLICY` to `PolicyType` enum in `policy_registry.py`
2. Add compatible types to `COMPATIBLE_TYPES` dict
3. Add a handler in `SemanticResolver._HANDLERS` in `semantic_resolver.py`
4. Add unit tests in `test_resolution.py`

### Add a New API Endpoint
1. Add route in the appropriate `routes_*.py`
2. Add Pydantic models in `models.py` if needed
3. Register in `app.py` if adding a new router file
4. Add API test in `test_api.py`

### Debug a Sync Issue
```bash
# Check conflict list
curl http://127.0.0.1:8000/api/v1/conflicts?status=all

# Inspect a specific replica
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"db_id": "db_inventory", "replica_id": "inventory_device_a", "sql": "SELECT * FROM products"}'
```
