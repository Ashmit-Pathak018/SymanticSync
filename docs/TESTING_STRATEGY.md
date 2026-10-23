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
| `test_resolution.py` | 11 | Basic resolver examples for the original seven policies; selected commutativity and edge cases (BOUNDED_SUM is covered separately) |

### 2. Integration Tests — CRDT Sync

End-to-end sync pipeline test.

**Location:** `backend/tests/test_sync.py`

The `INCREMENT` operation regressions in this module verify independent and
equal contributions, reverse delivery, duplicate replay after restart,
large-integer precision, same-process concurrent local calls, mixed concurrent
absolute SET review, trigger-induced rollback, the API operation receipt, and
post-manifest checkpoint-tail recovery. These tests cover explicit operation
semantics and do not establish arbitrary N-way convergence.

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

## Historical Baseline Test Count: 56 passed, 0 failed (superseded; not the current suite count)

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

`backend/tests/test_adversarial_resolution.py` uses deterministic seeded loops (not a property-testing framework). It checks pairwise commutativity for SUM, AVG, APPEND, LWW, MIN, MAX, and REJECT. LWW swaps values together with replica IDs and timestamps; APPEND swaps values together with replica IDs. Fixed-base integer SUM is tested for grouping associativity and non-idempotence. MIN/MAX associativity and idempotence assertions invoke the resolver. AVG has a concrete non-associativity counterexample and equal-input example. `backend/tests/test_bounded_operations.py::test_generated_bounded_sum_is_commutative_for_fixed_bounds` separately checks 250 seeded integer cases, comparing both status and candidate with the same fixed bounds; unsafe cases are flagged in both orders rather than clamped. These finite tests demonstrate only the stated inputs/properties, not general convergence. APPEND's resolver has no contribution identity; the separate repeat-sync test verifies one tracked two-replica schedule only.

Latest Phase 2 INSERT-collision verification: `test_insert_collision_resolution.py`, integrity, and mutation-conflict suites **58 passed**; full backend suite **153 passed**, one existing Starlette/httpx deprecation warning; `git diff --check` passed. Manual resolution tests cover selected two-replica histories only and do not prove general convergence or third-replica relay of collision resolutions.

### Category 10 — Phase 3 Bounded Operations and Mesh Schedules

- `test_bounded_operations.py` (25 cases) verifies explicit finite bounds, exact boundaries above $2^{53}$, ignored/mutating trigger rollback, signed-delta logging, local write rejection, overflow/underflow flagging without clamping, unsafe replay remaining pending, retry after a compensating operation and restart with exact receipt IDs/sequences, same-source reversed delivery, relay bounds verification, resolution relay idempotency, and a direct-SQL bypass boundary.
- `test_n_replica_sync.py` (12 schedules) exercises N=3 and N=5 replicas over star, ring, and complete-pair topologies, normal/reversed edge order, engine restart, and duplicate replay. All tested safe histories preserve the same final bounded value and exactly one receipt per operation ID.
- **Invariant safety** is verified for tracked writes and received delta materialization in these tested cases. Direct SQL can bypass bounds and operation metadata; the receiver rejects detected out-of-bound targets but cannot establish the history of untracked values.
- **Convergence:** These finite schedules are evidence only for enumerated safe histories. No arbitrary-order or general convergence guarantee is claimed. A delta whose next candidate violates bounds remains in the source log and is returned as rejected/pending until a later sync can safely apply it.
- **Verification History & Current Metrics:**
  - *Phase 3.1 Historical:* Focused suites 28 passed (16 bounded, 12 mesh); full backend suite 181 passed.
  - *Phase 3.3 Historical:* Focused suites 35 passed (23 bounded, 12 mesh); full backend suite 190 passed.
  - *Phase 3.4 Current:* Focused suites **36 passed** (24 bounded, 12 mesh); full backend suite **191 passed**, one existing Starlette/httpx deprecation warning. `git diff --check` passed.

### Category 11 — Phase 4/5 Remediation Evidence

- Phase 4 tests use generated seeded integer-SUM operations, execute tracked writes on two SQLite replicas, and run real `sync_replicas()` under LWW and SUM. SCR counts only conflict-row outcomes across both replicas; hand-built mixed fixtures prove correct non-conflict rows cannot inflate it, and zero conflicts produce N/A. Benchmark-row value agreement compares only ordered `bench_rows.value` observations; a test demonstrates that unrelated table state is outside this metric. Stress VRA is N/A because the generated workload has no domain range/FK constraints. Tests cover trial aggregation, reproducibility metadata, equivalent base images, paired trace identity, alternating order, timing boundaries, and JSON/CSV schemas. Generation tests cover each size and density; historical one-run and the completed two-trial-per-configuration matrix are distinguished below.
- Phase 5 tests verify FK enforcement before transactions, atomic nested quarantine, alternate UNIQUE parent references, composite child/FK identity, restored child rows and parent validation, invalid received INSERT/UPDATE rejection, paired/API/relayed RESOLVE deletes, duplicate received-delete idempotency, restart persistence, rollback on injected delete failure, parent-key update cascade versus rejection, fail-closed WITHOUT ROWID dependents, and SQL-console base-write/FK/declared-cascade behavior. The current focused FK module has 34 cases.
- Phase 6 `test_log_compaction.py` verifies persisted ACK vectors, missing/new replica pinning, exact-ID intersection, strict HLC boundary, dependency retention, transactional rollback, duplicate replay from compacted receipts, delayed/reversed three-replica relay, restart, snapshot bootstrap, and >70% row-count reduction in a 13-operation fixture. The current 42-case module also covers exact registry membership, post-manifest UPDATE/INSERT/DELETE/INCREMENT tail validation, malformed-tail state preservation, ACK conflict preflight and save-failure retry/restart, blocked-checkpoint isolation, snapshot binding, and lock coverage. It does not test power-loss at every filesystem boundary or full historical payload recovery.
- A fresh local Windows full-suite run after adding the increment artifact validator completed **332 passed, 1 warning in 77.43s** with `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-validator-20261020 -o faulthandler_timeout=30`. A subsequent local run completed **332 passed, 1 warning in 78.23s** with `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-full-local-20261020b -o faulthandler_timeout=30`. The warning was Starlette's HTTPX/TestClient deprecation. The same command under the sandbox stalled in Python 3.14 asyncio Windows socket-pair setup before the Starlette health endpoint; outside the sandbox it completed. No test was skipped or weakened.
- After adding the 13-seed pooled-summary utility and provenance regressions, the complete local backend suite completed **334 passed, 1 warning in 81.22s** using `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-full-13seed-20261020 -o faulthandler_timeout=30`. The warning was Starlette's HTTPX/TestClient deprecation. No tests were skipped or weakened.
- After adding the duplicate-seed rejection regression, the complete local backend suite completed **335 passed, 1 warning in 83.94s** using `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-full-13seed-final-20261020 -o faulthandler_timeout=30`. The warning was Starlette's HTTPX/TestClient deprecation. No tests were skipped or weakened.
- After adding single-run summary coverage, the complete local backend suite completed **336 passed, 1 warning in 85.15s** using `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-active-full-final-20261020 -o faulthandler_timeout=30`. The warning was Starlette's HTTPX/TestClient deprecation. No tests were skipped or weakened.
- Fresh focused Phase 6 run: `py -3.14 -m pytest backend/tests/test_log_compaction.py -q --tb=short --basetemp .pytest-increment-phase6-local-20261020` — **42 passed in 4.41s**. This verifies selected checkpoint recovery including the new post-manifest increment replay case; it is not a new Phase 6 sign-off and does not certify power-loss durability or multi-process coordination.
- Remaining boundaries: engine row addressing requires a single-column PK; composite parent-key targets are rejected. SQL-console writes have FK enforcement but no operation logging, quarantine, or shared-lock coverage; a default `NO ACTION` parent delete is rejected, while schema-declared cascades may delete dependent rows without quarantine. Use tracked deletion to preserve dependents in quarantine. Current benchmark data is synthetic SUM-only and finite schedule evidence, not general convergence or application-level capacity evidence.
- **Historical Phase 5 result:** focused replay/FK/bounded/N-replica tests passed **92**; full backend suite passed **241 tests** with one Starlette/httpx deprecation warning; `git diff --check` passed. Same-seed 5,000-op/20%-conflict SemanticSync sync measured **15.817 s**, **15.915 s**, and **16.097 s** across three runs. All are below the 30-second gate.
- **Phase 6 current laptop verification (user-reported; not rerun in this review):** `py -3.14 -m pytest backend/tests/test_log_compaction.py -q --tb=short --basetemp .pytest-tmp-laptop-phase6` completed with **41 passed in 3.30s**. `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-tmp-laptop-full -o faulthandler_timeout=10` completed with **309 passed, 1 warning in 75.06s**. Earlier local runs stalled during Windows/Python 3.14 Starlette `TestClient` startup after 13 tests; the later laptop result is separate evidence and does not erase that environment-specific history. The 13-operation row-reduction assertion is not a byte-level reduction or workload-wide claim. No `git diff --check` result was supplied or run in this review.
- **Historical single-trial matrices (seed 42; captured 2026-10-13; not repeated-trial evidence):** The original optimized records are preserved in `artifacts/benchmarks/historical-matrix-optimized-original-20261013/`; corrected-metric reruns are in `artifacts/benchmarks/historical-matrix-optimized-metric-corrected-20261013/`. Their values differ and they are distinct datasets. SCR in corrected runs scores conflict rows only across both replicas; RVAR compares ordered `bench_rows.value` only; stress VRA is N/A.

| Operations | Conflict density | Conflict rows | Baseline SCR % | SemanticSync SCR % | Baseline / SemanticSync RVAR % | Stress VRA | p50/p95/p99 ms | LWW sync s | SemanticSync sync s | Delta s | Log rows |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 1,000 | 5% | 50 | 0.00 | 98.00 | 100 / 100 | N/A | 3.34 / 3.75 / 4.04 | 1.010 | 1.033 | 0.023 | 2,098 |
| 1,000 | 20% | 200 | 0.00 | 97.50 | 100 / 100 | N/A | 3.31 / 3.76 / 4.93 | 2.957 | 3.254 | 0.297 | 2,390 |
| 1,000 | 50% | 500 | 0.00 | 98.20 | 100 / 100 | N/A | 3.31 / 3.75 / 4.07 | 6.919 | 7.096 | 0.177 | 2,982 |
| 5,000 | 5% | 250 | 0.00 | 98.00 | 100 / 100 | N/A | 3.45 / 3.88 / 4.35 | 10.669 | 10.740 | 0.071 | 10,490 |
| 5,000 | 20% | 1,000 | 0.00 | 98.00 | 100 / 100 | N/A | 3.45 / 3.93 / 4.43 | 23.582 | 23.700 | 0.118 | 11,960 |
| 5,000 | 50% | 2,500 | 0.00 | 98.16 | 100 / 100 | N/A | 3.46 / 3.94 / 4.51 | 50.143 | 50.056 | -0.087 | 14,908 |
| 10,000 | 5% | 500 | 0.00 | 98.20 | 100 / 100 | N/A | 3.58 / 4.15 / 4.64 | 36.156 | 35.727 | -0.429 | 20,982 |
| 10,000 | 20% | 2,000 | 0.00 | 98.25 | 100 / 100 | N/A | 3.59 / 4.13 / 4.63 | 68.028 | 68.166 | 0.138 | 23,930 |
| 10,000 | 50% | 5,000 | 0.00 | 97.70 | 100 / 100 | N/A | 3.60 / 4.20 / 4.67 | 138.337 | 139.082 | 0.745 | 29,770 |

- Raw JSON (workload, oracle, observed row states, and metrics) and CSV (metrics and per-write latencies) for corrected-metric runs are in `artifacts/benchmarks/historical-matrix-optimized-metric-corrected-20261013/`. The original optimized records are preserved in `artifacts/benchmarks/historical-matrix-optimized-original-20261013/`; their historical all-row SCR and old CR labels are stale under current metric definitions. Results are specific to this synthetic SUM workload and host. RVAR 100% means only that the two persisted replicas agreed on ordered `bench_rows.value` observations for these runs, not that full database state converged.

- **Updated paired trials (2026-10-14 to 2026-10-15; 2 trials/configuration; seed 42):** All nine configurations completed. Entries are measured medians with observed min–max ranges; batch times are seconds, delta and write p95 are milliseconds. These are descriptive summaries of two trial pairs, not inferential statistics.

| Operations | Density | LWW sync median [range] s | SemanticSync sync median [range] s | Paired delta median [range] ms | LWW / SemanticSync SCR % | RVAR % | SemanticSync write p95 median [range] ms |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 5% | 1.109 [1.091–1.127] | 1.132 [1.120–1.143] | 22.79 [16.31–29.26] | 0.0 / 98.0 | 100 / 100 | 4.15 [4.12–4.18] |
| 1,000 | 20% | 3.435 [3.333–3.537] | 3.363 [3.335–3.392] | -71.81 [-145.17–1.55] | 0.0 / 97.5 | 100 / 100 | 4.12 [4.05–4.18] |
| 1,000 | 50% | 7.881 [7.847–7.915] | 7.774 [7.766–7.782] | -107.20 [-149.34–-65.06] | 0.0 / 98.2 | 100 / 100 | 4.05 [4.02–4.08] |
| 5,000 | 5% | 11.345 [11.335–11.354] | 11.340 [11.228–11.451] | -5.02 [-107.00–96.97] | 0.0 / 98.0 | 100 / 100 | 4.37 [4.27–4.48] |
| 5,000 | 20% | 29.214 [25.044–33.384] | 32.019 [30.885–33.152] | 2,804.71 [-231.96–5,841.38] | 0.0 / 98.0 | 100 / 100 | 6.60 [6.31–6.90] |
| 5,000 | 50% | 74.180 [70.128–78.231] | 75.602 [72.763–78.440] | 1,421.64 [208.90–2,634.38] | 0.0 / 98.2 | 100 / 100 | 6.82 [6.56–7.08] |
| 10,000 | 5% | 76.220 [73.793–78.646] | 74.825 [73.058–76.593] | -1,394.30 [-2,053.43–-735.17] | 0.0 / 98.2 | 100 / 100 | 12.37 [12.10–12.64] |
| 10,000 | 20% | 118.678 [98.276–139.080] | 147.645 [143.627–151.664] | 28,967.53 [4,546.73–53,388.32] | 0.0 / 98.2 | 100 / 100 | 11.89 [11.76–12.02] |
| 10,000 | 50% | 193.364 [192.004–194.723] | 188.088 [184.699–191.476] | -5,276.10 [-10,024.15–-528.04] | 0.0 / 97.7 | 100 / 100 | 6.71 [6.69–6.73] |

Each cell has two paired trials. The batch delta is calculated per trial as SemanticSync sync minus LWW sync before calculating median and range. The 5,000/20% deltas (+5,841.38 ms and -231.96 ms) are notably variable; both are retained. These runs used the same digest within each pair, equivalent fresh initial rows, and alternating execution order. Artifacts for all nine cells are in `artifacts/benchmarks/repeated-stress-20261014/`. Do not combine these with the historical one-trial matrix. The workload is sequential tracked writes followed by batch synchronization; two trials do not establish statistical significance, concurrent-writer behavior, or general convergence.
