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

### 5. Core Correctness & Algebraic Properties Tests

Adversarial audit tests for policy mathematical laws, HLC monotonicity, and 3-replica pairwise convergence.

**Location:** `backend/tests/test_audit_correctness.py`

| File | Tests | Coverage |
|---|---|---|
| `test_audit_correctness.py` | 26 | Commutativity, non-associativity proofs, idempotency, HLC ordering |

### 6. Full Row-Mutation Conflict Tests (Phase 2)

Tests for full lifecycle row operations: INSERT vs INSERT (PK & UNIQUE collisions), UPDATE vs DELETE tombstones, DELETE vs DELETE idempotency, causality, and repeat-delivery.

**Location:** `backend/tests/test_mutation_conflicts.py`

| File | Tests | Coverage |
|---|---|---|
| `test_mutation_conflicts.py` | 15+ | INSERT collisions, UPDATE/DELETE, causal ordering, tombstones |

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

1. **Limited multi-replica sync evidence** — Phase 3 adds selected N=3/5 BOUNDED_SUM mesh schedules (Category 10). They do not establish arbitrary topology/order coverage or general convergence.
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

### Category 7 — Adversarial Audit Regression Tests (Phase 2 Audit)

A dedicated adversarial audit pass was performed after Phase 2 implementation. The following test classes were added to `test_mutation_conflicts.py` to cover previously untested edge cases and document confirmed bugs:

| Test Class | Scenarios Covered |
|---|---|
| `TestCausalityDocumented` | Single-sided clean delete (not flagged); UPDATE+DELETE always flagged (limitation documented); timestamps recorded; op context in explanation |
| `TestCompositePKSurfaced` | Composite-PK in `DetectResult.skipped_tables`; single-PK NOT in skipped (regression guard); `SyncResult.skipped_tables` populated |
| `TestStaleTombstonePropagation` | Mutated replica vs tombstone → `UPDATE_DELETE` conflict; unchanged stale copy receives durable tombstone; delayed delivery preserves explicit local updates; duplicate delivery is idempotent |

**Key adversarial scenarios documented by tests:**
- Composite-PK PRAGMA `pk == 1` bug and fix (`pk > 0` required).
- `DELETE_WINS` increments `auto_resolved` only after confirmed delete (not on exception).
- UPDATE timestamps are retrieved from column-level keys, not `"*"` key.
- Causality in UPDATE vs DELETE is informational (timestamps + op_map), not auto-exempting.
- Tombstones propagate only when receiver contents match the deleted snapshot and its change log has no row operation; explicit local changes remain reviewable.

### Category 8 — Phase 2.2–2.4 Integrity and Propagation Regressions

`backend/tests/test_phase_2_2_integrity.py` covers Phase 2.2 integrity and Phase 2.3–2.4 propagation cases:

| Area | Scenarios |
|---|---|
| Tombstone ordering and identity | Delete then reinsert; A→B→C after engine restart; C→B→A; repeated delivery by origin ID |
| Atomic tombstone delivery | Injected tombstone-log failure rolls back deletion; writer contention revalidates after the competing local change commits |
| Composite keys | A recorded DELETE for a composite-PK table is skipped without modifying rows; direct delete rejects the table |
| Conflict write-back | Row-level NULL deletes both replicas and writes matching tombstone identities; cell-level NULL stores SQL NULL; missing row fails unresolved; failure on replica B rolls back replica A in both API and engine paths |
| Sync API | `skipped_tables` appears in the JSON result for the UI |
| INSERT integrity | Receiver rejects and rolls back ignored and row-mutating triggers before recording receipt |
| Resolution relay | Shared RESOLVE identity, sequence, and dependencies relay to a third replica when either peer arrives first |
| Retry recovery | Earlier receipts remain safe after a later operation fails; retry applies only the outstanding operation |
| Invalid resurrection payload | `None` and non-dictionary payloads remain unresolved; replica rows and logs stay unchanged |
| Resolution receipt identity | Third-replica receipt metadata matches both peers and duplicate relay leaves exactly one receipt |

Phase 2.3 additionally covers INSERT/UPDATE relay, reverse pair order, duplicate operation delivery, delayed stale deletes, delete/reinsert, restart recovery, and preservation of a tracked concurrent local edit. These tests exercise selected histories; they do not prove general convergence.

Phase 2.3–2.4 tests cover selected histories and relay orders; they do not prove general convergence.

Phase 2.4 final-fix verification at that point: focused integrity and mutation-conflict suites **47 passed**; full backend suite **129 passed**, one existing Starlette/httpx deprecation warning; frontend production build succeeded; `git diff --check` passed.

### Category 9 — Phase 1 Generated Adversarial Resolution Tests

`backend/tests/test_adversarial_resolution.py` uses seeded generated inputs and verifies only mathematically valid properties: commutativity for all policies, fixed-base SUM associativity, MIN/MAX associativity and idempotence, and AVG's non-associativity. It documents SUM's non-idempotency and APPEND's limited duplicate behavior. Boundary cases cover empty text, Unicode content/delimiters, `None`, duplicate sync delivery, malformed policy values, transaction rollback, and `BEGIN IMMEDIATE` before tracked table access.

Latest Phase 2 INSERT-collision verification: `test_insert_collision_resolution.py`, integrity, and mutation-conflict suites **58 passed**; full backend suite **153 passed**, one existing Starlette/httpx deprecation warning; `git diff --check` passed. Manual resolution tests cover selected two-replica histories only and do not prove general convergence or third-replica relay of collision resolutions.

### Category 10 — Phase 3 Bounded Operations and Mesh Schedules

- `test_bounded_operations.py` (24 cases) verifies explicit finite bounds, exact boundaries above $2^{53}$, ignored/mutating trigger rollback, signed-delta logging, local write rejection, overflow/underflow flagging without clamping, unsafe replay remaining pending, retry after a compensating operation and restart with exact receipt IDs/sequences, same-source reversed delivery, relay bounds verification, resolution relay idempotency, and a direct-SQL bypass boundary.
- `test_n_replica_sync.py` (12 schedules) exercises N=3 and N=5 replicas over star, ring, and complete-pair topologies, normal/reversed edge order, engine restart, and duplicate replay. All tested safe histories preserve the same final bounded value and exactly one receipt per operation ID.
- **Invariant safety** is verified for tracked writes and received delta materialization in these tested cases. Direct SQL can bypass bounds and operation metadata; the receiver rejects detected out-of-bound targets but cannot establish the history of untracked values.
- **Convergence:** These finite schedules are evidence only for enumerated safe histories. No arbitrary-order or general convergence guarantee is claimed. A delta whose next candidate violates bounds remains in the source log and is returned as rejected/pending until a later sync can safely apply it.
- **Verification History & Current Metrics:**
  - *Phase 3.1 Historical:* Focused suites 28 passed (16 bounded, 12 mesh); full backend suite 181 passed.
  - *Phase 3.3 Historical:* Focused suites 35 passed (23 bounded, 12 mesh); full backend suite 190 passed.
  - *Phase 3.4 Current:* Focused suites **36 passed** (24 bounded, 12 mesh); full backend suite **191 passed**, one existing Starlette/httpx deprecation warning. `git diff --check` passed.

### Category 11 — Phase 4/5 Remediation Evidence

- Phase 4 tests use generated seeded integer-SUM operations, execute tracked writes on two SQLite replicas, run real `sync_replicas()` under LWW and SUM, and independently recompute SCR/VRA/CR from JSON-exported oracle and persisted final states. Tracked-write p50/p95/p99, baseline and SemanticSync sync time, measured log rows, reproducibility digest, and JSON/CSV artifact content are checked. Generation tests cover each required size and density; measured full-matrix results are recorded separately because large runs are expensive.
- Phase 5 tests verify FK enforcement before transactions, atomic nested quarantine, alternate UNIQUE parent references, composite child/FK identity, restored child rows and parent validation, invalid received INSERT/UPDATE rejection, paired and API resolution deletes, duplicate received-delete idempotency, restart persistence, and rollback on injected delete failure.
- Phase 6 `test_log_compaction.py` verifies persisted ACK vectors, missing/new replica pinning, exact-ID intersection, strict HLC boundary, dependency retention, transactional rollback, duplicate replay from compacted receipts, delayed/reversed three-replica relay, restart, snapshot bootstrap, and >70% row-count reduction in a 13-operation fixture. It does not test power-loss at every filesystem boundary or full historical payload recovery.
- Remaining boundaries: engine row addressing requires a single-column PK; composite targets are rejected. SQL console direct parent deletes fail under FK enforcement but do not enter tracked quarantine; users must use tracked delete paths to preserve dependent rows. Current benchmark data is synthetic SUM-only and finite schedule evidence, not general convergence or application-level capacity evidence.
- **Historical Phase 5 result:** focused replay/FK/bounded/N-replica tests passed **92**; full backend suite passed **241 tests** with one Starlette/httpx deprecation warning; `git diff --check` passed. Same-seed 5,000-op/20%-conflict SemanticSync sync measured **15.817 s**, **15.915 s**, and **16.097 s** across three runs. All are below the 30-second gate.
- **Phase 6 current result:** `test_log_compaction.py` **12 passed**; full backend suite **253 passed**, one existing Starlette/httpx deprecation warning. `git diff --check` passed. The row-reduction assertion is for a 13-operation fixture; no byte-level reduction claim is made.
- **Optimized measured matrix (seed 42; latency is tracked-write p50/p95/p99 in ms; overhead = SemanticSync sync − LWW sync; change-log rows are total across both SemanticSync replicas):**

| Operations | Conflict density | Conflicts | SCR % | VRA % | CR % | p50/p95/p99 ms | LWW sync s | SemanticSync sync s | Overhead s | Log rows |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 5% | 50 | 99.90 | 98.00 | 100.00 | 3.18 / 3.75 / 4.02 | 0.775 | 0.698 | -0.076 | 2,098 |
| 1,000 | 20% | 200 | 99.50 | 97.50 | 100.00 | 2.99 / 3.47 / 5.03 | 1.990 | 1.989 | -0.000 | 2,390 |
| 1,000 | 50% | 500 | 99.10 | 98.20 | 100.00 | 2.98 / 3.42 / 4.19 | 4.623 | 4.527 | -0.096 | 2,982 |
| 5,000 | 5% | 250 | 99.90 | 98.00 | 100.00 | 2.98 / 3.42 / 3.98 | 7.055 | 7.091 | 0.036 | 10,490 |
| 5,000 | 20% | 1,000 | 99.60 | 98.00 | 100.00 | 3.07 / 3.57 / 4.51 | 15.810 | 16.097 | 0.287 | 11,960 |
| 5,000 | 50% | 2,500 | 99.08 | 98.16 | 100.00 | 3.03 / 3.51 / 4.05 | 33.338 | 33.964 | 0.625 | 14,908 |
| 10,000 | 5% | 500 | 99.91 | 98.20 | 100.00 | 3.10 / 3.62 / 4.29 | 24.514 | 24.291 | -0.223 | 20,982 |
| 10,000 | 20% | 2,000 | 99.65 | 98.25 | 100.00 | 3.01 / 3.49 / 3.95 | 46.510 | 48.561 | 2.051 | 23,930 |
| 10,000 | 50% | 5,000 | 98.85 | 97.70 | 100.00 | 2.99 / 3.43 / 3.84 | 91.642 | 94.013 | 2.371 | 29,770 |

- Raw JSON (workload, oracle, observed row states, and metrics) and CSV (metrics and per-write latencies) for the optimized runs are in `.codex-phase4-optimized-matrix-20261013/`; the prior baseline matrix remains in `.codex-phase4-matrix-20261013/`. Results are specific to this synthetic SUM workload and host; 100% CR means the two persisted replicas agreed for these schedules, not a general convergence proof.
