# SemanticSync — Testing Strategy

**Version:** 1.0

---

## Testing Philosophy

> "Test the behavior, not the implementation."

SemanticSync prioritizes **behavioral** and **integration** tests over mocking. Every test uses real SQLite databases (via `tmp_path` fixtures) and real engine components — not mocked objects.

---

## Test Categories

### 1. Unit Tests — Engine Layer

Tests for individual engine components in isolation.

**Location:** `backend/tests/test_schema.py`, `test_validation.py`, `test_resolution.py`

| File | Tests | Coverage |
|---|---|---|
| `test_schema.py` | 32 | SchemaInspector: type normalization, PRAGMA parsing, error handling |
| `test_validation.py` | 4 | PolicyValidator: all valid combinations, all invalid combinations |
| `test_resolution.py` | 10 | SemanticResolver: all 7 policies, commutativity, edge cases |

### 2. Integration Tests — CRDT Sync

End-to-end sync pipeline test.

**Location:** `backend/tests/test_sync.py`

| File | Tests | Coverage |
|---|---|---|
| `test_sync.py` | 1 | CRDTSyncEngine: full create-diverge-sync convergence cycle |

### 3. Workload / Benchmark Tests

Tests that validate workload setup and ground truth scenarios.

**Location:** `backend/tests/test_benchmark.py`

| File | Tests | Coverage |
|---|---|---|
| `test_benchmark.py` | 3 | Inventory, Notes, Health workloads: setup, ground truth count, SCR |

### 4. API Integration Tests

Tests against the running FastAPI app using `starlette.TestClient`.

**Location:** `backend/tests/test_api.py`

| File | Tests | Coverage |
|---|---|---|
| `test_api.py` | 6 | Health check, seed, database registration, schema, policy, query |

---

## Current Test Count: 56 passed, 0 failed

| Category | Count |
|---|---|
| Schema inspection | 32 |
| Policy validation | 4 |
| Semantic resolution | 10 |
| CRDT sync | 1 |
| Workload benchmark | 3 |
| API integration | 6 |
| **Total** | **56** |

---

## How to Run Tests

```bash
# From project root: c:\Users\ASMIT\SemanticSync

# Run all tests
python -m pytest backend/tests/ -v

# Run specific file
python -m pytest backend/tests/test_resolution.py -v

# Run with short traceback
python -m pytest backend/tests/ -v --tb=short

# Run and show print output
python -m pytest backend/tests/ -v -s

# Run only tests matching a pattern
python -m pytest backend/tests/ -k "test_sum" -v
```

---

## Key Test Patterns

### Pattern 1: Real SQLite with `tmp_path`
```python
def test_inspect_table(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, qty INTEGER)")
    conn.close()

    inspector = SchemaInspector(str(db))
    columns = inspector.inspect_table("products")
    assert columns[0].normalized_type == "INTEGER"
    assert columns[0].is_pk == True
```

### Pattern 2: Commutativity Testing
```python
def test_sum_commutativity():
    resolver = SemanticResolver()
    result_ab = resolver.resolve(PolicyType.SUM, 100, 115, 120, ...)
    result_ba = resolver.resolve(PolicyType.SUM, 100, 120, 115, ...)
    assert result_ab.resolved_value == result_ba.resolved_value
```

### Pattern 3: API via TestClient
```python
def test_health():
    from starlette.testclient import TestClient
    from backend.app import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
```

---

## Coverage Goals

| Component | Target Coverage |
|---|---|
| `engine/schema_inspector.py` | 95%+ |
| `engine/policy_validator.py` | 100% |
| `engine/semantic_resolver.py` | 100% |
| `engine/crdt_sync.py` | 70%+ |
| `api/routes_*` | 60%+ |
| `workloads/` | 80%+ |

---

## Known Test Limitations

1. **No multi-replica sync tests** — `test_sync.py` tests only 2-replica convergence. Multi-replica (3+) sync is not tested.
2. **Starlette deprecation warning** — `Using httpx with starlette.testclient is deprecated; install httpx2 instead`. Tests still pass — cosmetic warning only.
3. **No network transport tests** — SemanticSync has no network layer; all tests run against local files.
4. **No mutation testing** — No `mutmut` or `cosmic-ray` mutation testing yet.

---

## CI Considerations

For a future CI pipeline:
```yaml
# .github/workflows/test.yml
- name: Run Tests
  run: python -m pytest backend/tests/ -v --tb=short
  working-directory: c:\Users\ASMIT\SemanticSync
```
