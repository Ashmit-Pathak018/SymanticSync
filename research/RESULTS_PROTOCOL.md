# SemanticSync — Results Protocol & Empirical Telemetry

**Version:** 2.1 (Artifact-audited)
**Status:** Repeated stress artifacts validated for internal consistency; measurements not reproduced in this audit.

## 1. Evidence categories

| Status | Meaning |
|---|---|
| **Measured** | Produced by an actual run and retained with its records. |
| **Artifact-validated** | Saved JSON/CSV records passed consistency checks; this does not reproduce the run. |
| **Target** | Planned objective, not a measured result. |
| **Unverified** | Available evidence cannot establish the claim. |

## 2. Domain runner status

The domain-runner endpoint evaluates resolver-level fixtures and uses a replica-B LWW proxy; its former comparative and convergence fields were not validated as an end-to-end comparison. Those outputs are excluded from empirical conclusions. The endpoint is marked illustrative/unvalidated. No replacement domain measurements are reported here.

## 3. Scaled stress evidence

The 2026-10-13 Phase 4 matrix is historical single-trial evidence. The separate repeated records in `artifacts/benchmarks/repeated-stress-20261014/` cover all nine configurations with two paired trials each. The harness performs real tracked writes and pairwise synchronization on fresh equivalent SQLite replicas, using paired identical seeded traces and alternating execution order.

The following values remain historical targets only; they are not acceptance results for the repeated matrix:

| Workload size | Conflict density | Target baseline SCR | Target SemanticSync SCR | Target p95 latency |
|---|---:|---:|---:|---:|
| 1,000 | 5% | ≤35% | ≥95% | <0.5 ms |
| 1,000 | 20% | ≤35% | ≥95% | <0.8 ms |
| 10,000 | 50% | ≤35% | ≥90% | <1.5 ms |

SCR is conflict-row correctness against the additive oracle, scored across both replicas; non-conflict rows are excluded, and zero-conflict SCR is undefined (`null`). RVAR compares ordered `bench_rows.value` observations only; it is not full-database convergence. VRA is unmeasured. The workload consists of sequential tracked writes followed by one batch sync per system per trial, not concurrent writers. Summaries are descriptive for two samples and do not establish significance, a general performance advantage, or general convergence.

## 4. Artifact validation (no benchmark run)

From the repository root:

```powershell
python -m backend.workloads.validate_repeated_benchmark_artifacts
```

The standard-library-only validator reads the nine JSON/CSV pairs in `artifacts/benchmarks/repeated-stress-20261014/`. It checks configuration coverage, paired-trial counts, operation digests and workload metadata, alternating order, raw timing records, paired deltas, metric definitions, and JSON/CSV summaries. A successful validation establishes internal consistency of saved records, not that measurements were reproduced. A different artifact directory may be passed as the command's sole argument.

## 5. Experiment reproduction (expensive; not run in this audit)

Install backend dependencies using the README instructions, then run from the repository root with a new output directory; do not reuse the saved-artifact directory:

```powershell
python -c "from backend.workloads.stress_harness import StressBenchmarkConfig, StressHarness; from datetime import datetime; from pathlib import Path; out=Path('artifacts/benchmarks/reproduction-run-'+datetime.now().strftime('%Y%m%d-%H%M%S')); [(StressHarness(StressBenchmarkConfig(num_operations=n, conflict_density=d, seed=42, trials=2, output_dir=str(out))).run_benchmark()) for n in (1000, 5000, 10000) for d in (0.05, 0.20, 0.50)]"
```

This runs nine configurations and two trials for each system/configuration (18 paired trial records). For each config, the harness uses `random.Random(42)`, `round(n*density)` conflict rows, base value 100, independently generated integer deltas from 1 through 50, and a seeded shuffle. Both systems receive the same operation list and fresh equivalent bases. Trial one runs LWW then SemanticSync; trial two reverses the order. Writes are sequential. Tracked-write timing encloses individual `apply_change` calls; batch-sync timing encloses `sync_replicas`; the paired delta is SemanticSync batch-sync milliseconds minus LWW batch-sync milliseconds.

The harness records Python/platform/machine/processor strings, SQLite runtime version, seed and workload parameters, journal mode, per-replica FK status, and workload digest. Existing records identify Windows 11, Python 3.14.3, SQLite 3.50.4, DELETE journaling, and seed 42. They do not retain exact Python package versions, storage type, memory, or host load. `backend/requirements.txt` specifies version ranges, not a lockfile; cross-machine or future reruns may differ. The existing artifacts include all nine JSON/CSV pairs but have minor schema variation: redundant top-level `engine_settings` is absent in four JSON files, while the corresponding trial-level settings are present and validated.

The validator and experiment are distinct workflows: validation reads existing data only; reproduction creates new measurements and must use a separate output directory.
