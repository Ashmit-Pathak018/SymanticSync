# Reproduction and Artifact Validation

**Status:** The saved historical matrix was validator-checked; a separate small, exploratory engine-level pilot was executed on 2026-10-20. The nine-cell matrix was not regenerated. This document distinguishes these workflows and does not treat the pilot as confirmatory evidence.

## Environment captured locally

The 2026-10-20 Windows environment and exact installed Python package snapshot are recorded in `ENVIRONMENT-WINDOWS-PY314-20261020.txt`. Frontend dependencies are defined by `frontend/package.json` and the committed `frontend/package-lock.json`; run `npm ci` from `frontend/` for a lockfile-based install. Backend dependencies in `backend/requirements.txt` are version ranges, not a lockfile. The captured package list is an environment snapshot, not a portable pinned backend dependency lock.

Observed versions: Windows 11, Python 3.14.3, SQLite 3.50.4, FastAPI 0.143.0, Starlette 1.7.0, Uvicorn 0.54.0, Pydantic 2.13.4, HTTPX 0.28.1, pytest 9.1.1, Node.js 24.13.1, npm 11.8.0, Vite 8.3.4, Vitest 5.0.3, React 19.3.0.

Hardware storage type, physical memory, CPU model/core use, thermal/power state, and host load were not recorded for saved historical/repeated measurements. They cannot be reconstructed from the artifacts.

## Validate saved repeated artifacts (does not run a benchmark)

From the repository root in PowerShell:

```powershell
py -3.14 -m backend.workloads.validate_repeated_benchmark_artifacts
```

An optional artifact directory can be passed as the validator's only argument. The current saved directory is `artifacts/benchmarks/repeated-stress-20261014/`. The validator checks records and summaries only; a pass does not reproduce a measurement.

## Run the current synthetic harness (measurement run)

The current production harness accepts 2–10 repeated trials but reuses one seed/trace per configuration across those trials. Its run is sequential tracked writes followed by batch pairwise sync. Example command for a new output directory:

```powershell
py -3.14 -c "from backend.workloads.stress_harness import StressBenchmarkConfig, StressHarness; from pathlib import Path; out=Path('artifacts/benchmarks/new-run'); [(StressHarness(StressBenchmarkConfig(num_operations=n, conflict_density=d, seed=42, trials=2, output_dir=str(out))).run_benchmark()) for n in (1000, 5000, 10000) for d in (0.05, 0.20, 0.50)]"
```

This example is the existing two-trial same-seed protocol; it is not the proposed independent-seed experiment in `research/experiments/EXPERIMENTAL_PROTOCOL.md`. Use an empty/new output directory. Do not treat the LWW-vs-SUM SCR contrast as a neutral comparison: the oracle is additive. Do not claim full-database convergence, concurrent-writer performance, significance, or general advantage.

The nine saved JSON/CSV configurations are already artifact-validated. No expensive matrix was regenerated during this audit. A research-grade independent-seed matrix needs an explicit driver or harness extension that records a distinct seed and digest per paired trial; that implementation and run remain outstanding.

## Tests and build

Commands executed locally in the current dirty worktree on 2026-10-20:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-fb45a2a96f434ead9e22f955e4f89a7f -o faulthandler_timeout=15
npm test -- --reporter=dot --pool=threads --maxWorkers=1
npm run build
```

Observed outcomes: backend **314 passed, 1 warning in 75.80s**; frontend **3 files / 15 tests passed**; production build passed. The backend run emitted faulthandler stack dumps while long stress tests ran, but completed; the warning was a Starlette deprecation about HTTPX/TestClient. These are environment-specific results on the dirty worktree, not a fresh clean-checkout artifact build.

After adding an engine-level equal-assignment characterization test, the full backend suite was freshly rerun locally:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-20261020 -o faulthandler_timeout=20
```

Observed historical result at that point: **319 passed, 1 warning in 94.77s**. After runner/provenance changes, another historical run completed:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-current-20261020 -o faulthandler_timeout=20
```

That historical result was **319 passed, 1 warning in 92.61s**. After adding explicit `INCREMENT`, the complete suite was run locally outside the sandbox:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-local-20261020 -o faulthandler_timeout=30
```

That run completed with **331 passed, 1 warning in 77.49s**. After adding the increment artifact validator tests, the suite was rerun locally:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-final-validator-20261020 -o faulthandler_timeout=30
```

Earlier observed results were **332 passed, 1 warning in 77.43s**, **332 passed, 1 warning in 78.23s**, **334 passed, 1 warning in 81.22s**, and **335 passed, 1 warning in 83.94s**. After adding single-run summary coverage, the latest observed result is **336 passed, 1 warning in 85.15s**, from `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-active-full-final-20261020 -o faulthandler_timeout=30`. The warning was Starlette's HTTPX/TestClient deprecation. No tests were skipped. The run used the dirty Windows worktree; it is not a clean-checkout build.

## Exploratory independent-seed engine pilot

The pilot driver is separate from the production synthetic stress harness. It compared a narrow direct-SQL scalar additive implementation with the actual engine SUM and LWW paths under one shared generated trace per trial. The direct-SQL path omits operation identity, receipts, conflict persistence, FK quarantine, and checkpoints; consequently this is not a fair end-to-end performance comparison. The workload remains sequential writes followed by a batch sync.

Executed command:

```powershell
py -3.14 -m research.experiments.engine_evaluation --operations 1000 --density 0.05 --trials 3 --seed 20261020 --output-dir research/experiments/runs/pilot-1000-5pct-20261020-final1
```

The run completed three trials with seeds 20261020–20261022 and distinct workload digests. JSON/CSV outputs and the trial database directories are retained at `research/experiments/runs/pilot-1000-5pct-20261020-final1/`. Engine SUM conflict SCR was 100%, 98%, and 96%; RVAR was 100% each time. The below-100 results expose equal-valued assignments that the additive oracle treats as independent contributions while the state-diff detector does not treat them as conflicts. The paired engine-SUM minus direct-SQL sync deltas were +1031.355, +1129.018, and +973.396 ms, but are not interpreted as comparative overhead because the paths provide different guarantees and the additive operation intent is unresolved. The pilot is exploratory and excluded from manuscript empirical conclusions.

The `final1` artifact predates run-captured Git/source fingerprints. The current driver records Git revision, dirty state, and SHA-256 hashes of relevant engine and runner sources. A fingerprint cannot be safely added to an already completed raw run, so `final1` retains this provenance limitation.

The same seed set was rerun after source snapshotting was added, using a separate output directory:

```powershell
py -3.14 -m research.experiments.engine_evaluation --operations 1000 --density 0.05 --trials 3 --seed 20261020 --output-dir research/experiments/runs/pilot-1000-5pct-20261020-source-recorded
```

This completed three trials and recorded Git revision `5e98f43c972410f3403d06a27bd4bb4620a762a2`, a dirty-worktree flag, and five relevant source hashes. It reproduced the same workload digests, SUM SCR values, and mismatch counts as `final1`; it reused the same seeds and is not an additional independent sample. Its separate timing records are retained and not pooled with the first run.

## Explicit operation-intent and scale-feasibility pilots

After the tracked `INCREMENT` operation was added, separate pilots used explicit increment records rather than trying to infer contribution intent from absolute `SET` values. The original three-seed and later ten-seed 1k/5% raw runs, including their JSON/CSV/database records, are documented in `research/experiments/PILOT_FINDINGS.md`. Each raw run can be checked without rerunning it:

```powershell
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/increment_evaluation_1000_5pct.json
```

The records share the same captured source hashes, Git revision, runtime environment, configuration, and metric definitions, and have 13 unique seeds/digests. The validated descriptive aggregation is regenerated with the command in `research/experiments/runs/README.md`; it reports a paired engine-INCREMENT minus direct-SQL-SUM batch-sync delta median of 409.585 ms (IQR 406.599–424.612 ms, range 389.840–450.654 ms; mean 415.805 ms, sample SD 17.625 ms). This is not a fair end-to-end comparison because the direct SQL path omits system guarantees; no significance or advantage claim follows.

Additional 1k cells at 20% and 50% each completed 10 independent trials with fresh state and balanced order. Their validation and summary regeneration commands are in `research/experiments/runs/README.md`; derived summaries are stored separately by density. Together, the 1k explicit-INCREMENT study has 13, 10, and 10 trials at 5%, 20%, and 50%. It does not cover 5k/10k configurations; the full matrix remains incomplete. All paired deltas against direct-SQL SUM remain diagnostic because the baseline omits system guarantees.

Two one-trial scale-feasibility runs were later executed with the same experiment driver. These commands record the original runs; use a new output directory when generating new measurements:

```powershell
py -3.14 -m research.experiments.increment_evaluation --operations 5000 --density 0.20 --trials 1 --seed 20261030 --output-dir research/experiments/runs/increment-runtime-pilot-20261020/5000-20pct
py -3.14 -m research.experiments.increment_evaluation --operations 10000 --density 0.20 --trials 1 --seed 20261031 --output-dir research/experiments/runs/increment-runtime-pilot-20261020/10000-20pct
```

Both saved records are validated using the commands in `research/experiments/runs/README.md`. Observed full trial durations were 90.113 s and 226.433 s, respectively. These are single local observations, not a scaling model or performance comparison. The 10k run took 47.491 s in the explicit-INCREMENT batch synchronization phase. This cost makes the proposed nine-configuration, ten-seed study expensive; the full matrix has not been run. These diagnostics are excluded from manuscript empirical results.

## Results and limitations

- Current repeated trials have two observations per configuration and one workload seed per configuration. Statistics are descriptive only.
- `SCR` is correctness on conflict rows against an additive oracle; `RVAR` compares ordered `bench_rows.value` only; `VRA` is unmeasured.
- Timing boundaries and missing environment data are documented in `research/experiments/METRIC_DEFINITIONS.md`.
- No fair same-semantics end-to-end baseline, ablation, complete crash-fault campaign, or formal correctness proof is available.
- Backend dependencies are not fully locked. Full clean-machine reproduction is therefore not yet established.
