# Repository Baseline

**Captured:** 2026-10-20 (local Windows workspace)
**Purpose:** Record the inspected implementation and evidence before expanding the research evaluation. This is a working-tree snapshot, not a clean-release claim.

## Repository state

- Repository: `C:\Users\ASMIT\SemanticSync`
- Branch: `main`
- `HEAD`: `5e98f43c972410f3403d06a27bd4bb4620a762a2`
- The worktree was already extensively modified and partly staged before this audit. No existing changes were reset, unstaged, overwritten, or discarded. The repository is not a clean checkout, so test/evidence attribution to `HEAD` alone would be inaccurate.
- Git status included existing changes across backend, frontend, documentation, manuscript, and benchmark artifact migrations, plus untracked local test scratch directories. The status snapshot is available in the session history; generated test scratch was left untouched.

## Runtime and dependencies observed

Backend test/runtime environment:

| Component | Observed version |
|---|---|
| Python | 3.14.3 (Windows x86-64) |
| SQLite runtime | 3.50.4 |
| FastAPI | 0.143.0 |
| Starlette | 1.7.0 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.13.4 |
| HTTPX | 0.28.1 |
| pytest | 9.1.1 |
| Node.js | 24.13.1 |
| npm | 11.8.0 |
| Vite | 8.3.4 |
| Vitest | 5.0.3 |
| React / React DOM | 19.3.0 / 19.3.0 |

The backend requirements are ranges in `backend/requirements.txt`, not a fully pinned lockfile. Frontend exact installed versions were inspected with `npm ls --depth=0`; the project has a package lock. No hardware storage type, available-memory measurement, host-load measurement, or CPU benchmark was recorded and none is inferred here.

## Implementation map verified from source

- FastAPI application and API contracts: `backend/app.py`, `backend/api/`.
- SQLite tracked writes, operation replay, pairwise sync, conflict detection/resolution: `backend/engine/crdt_sync.py`, `backend/engine/semantic_resolver.py`, `backend/engine/policy_registry.py`.
- Follow-up: `CRDTSyncEngine.apply_increment` and `POST /api/v1/sync/increment` now record explicit additive operation identity separately from absolute `apply_change`/SET. Focused coverage is in `backend/tests/test_sync.py`, `backend/tests/test_log_compaction.py`, and `backend/tests/test_increment_evaluation.py`.
- Foreign-key quarantine and SQLite connection setup: `backend/engine/fk_quarantine.py`, `backend/api/routes_quarantine.py`, plus tracked engine routes.
- Checkpoint store, locking, log pruning, and recovery: `backend/engine/checkpoint_store.py`, `backend/engine/mutation_lock.py`, `backend/engine/log_compaction.py`, and `backend/api/routes_sync.py`.
- Synthetic stress workload and saved-run export: `backend/workloads/stress_harness.py`; saved JSON/CSV validation: `backend/workloads/validate_repeated_benchmark_artifacts.py`.
- Domain benchmark endpoint: `backend/api/routes_benchmark.py`; it reports `evaluation_status="illustrative_unvalidated"` and null comparative metrics.
- Research manuscript sources include `docs/MANUSCRIPT.md`, `docs/MANUSCRIPT.html`, `docs/manuscript_latex/main.tex`, and `docs/manuscript_latex/references.bib`. The repository currently has multiple manuscript representations; consistency remains a release risk unless the documented production path is followed.

## Current measured-workload boundary

The stress harness builds a fresh base table for each system/trial, uses the same generated trace for both systems in a pair, performs sequential tracked writes, then times one pairwise batch synchronization. The saved repeated matrix has nine configurations (1k/5k/10k operations × 5%/20%/50%) and two paired trials per configuration. All trials currently reuse seed 42 and the same workload digest within each configuration; they are repeated execution timings, not independent workload-seed samples.

SCR is conflict-only correctness under the benchmark's additive oracle, scored across both replicas; the denominator is twice the conflict-row count. RVAR compares only `bench_rows.value` by row order. VRA is null/unmeasured. The LWW system is evaluated against an additive oracle, so its observed 0% SCR is a workload-oracle mismatch with LWW semantics and cannot establish broad policy superiority. The workload is not concurrent-writer or contention testing.

## Verification executed in this local workspace

- Full backend suite had already completed locally during the active work: `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-fb45a2a96f434ead9e22f955e4f89a7f -o faulthandler_timeout=15` — **314 passed, 1 warning in 75.80s**. Faulthandler emitted timeout stack dumps during long real stress workload tests; the process continued and completed successfully. The warning was a Starlette deprecation warning about HTTPX/TestClient compatibility. This is a run on the then-current dirty worktree, not a clean release build.
- The latest full local backend run after adding the increment artifact validator completed with `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-validator-20261020 -o faulthandler_timeout=30` — **332 passed, 1 warning in 77.43s**. The run used the dirty worktree and local Windows Python 3.14 environment. The warning was Starlette's HTTPX/TestClient deprecation; no tests were skipped.
- Saved artifact validation was executed locally: `py -3.14 -m backend.workloads.validate_repeated_benchmark_artifacts` — **passed**, 9 configurations, 18 JSON/CSV files, 18 paired trials; it did not run a benchmark.
- Frontend tests and build were executed locally in the same work session: `npm test -- --reporter=dot --pool=threads --maxWorkers=1` — 3 files / 15 tests passed; `npm run build` passed. These results are environment-specific and do not constitute end-to-end browser verification.
- No new benchmark matrix was run for this baseline capture.

## Follow-up on the equal-assignment oracle boundary

The implementation now includes a separate tracked `INCREMENT` operation so additive intent is explicit. The historical benchmark generator and saved artifacts remain SET-based and were not modified. The final three-seed exploratory run for 1,000 operations at 5% density using explicit increments is stored in `research/experiments/runs/increment-pilot-1000-5pct-20261020-final/`; earlier attempts remain separately preserved. This one-cell pilot is not confirmatory and does not resolve the limits of the historical SCR result.

## Source fingerprints

SHA-256 fingerprints observed during this audit (working-tree file contents):

| File | SHA-256 |
|---|---|
| `backend/workloads/stress_harness.py` | `e99fa8803598fb0bbb7480880c1ed27b49aaee76c05c5e6c128ce967e5561fed` |
| `backend/engine/crdt_sync.py` | `4b03d0becacf3daf0e232dc8596cc0c31b3691e113e250d46098691361233f6f` |
| `backend/engine/log_compaction.py` | `cbb570046645754740c851f6c4cea2c7fc02bb2dc766317ad7e8dd80d380554b` |
| `backend/engine/checkpoint_store.py` | `b15677169151755db89eb0147a37c4510cce464210a97aceb80fb32a6092a20e` |
| `docs/MANUSCRIPT.md` | `920e4554b61dc4dd2f17da6ea4fac2cdf588bdb9ff246633eadf6f4f8840c823` |
| `docs/manuscript_latex/references.bib` | `ed42ae179f275f92f557cf92c9ecb8a9e7d6af3429aed1fee0c5f6459dbda4af` |

These hashes are local fingerprints for the files as inspected; later edits require a new fingerprint.
