# Research Run Records

These folders preserve attempted local runs. They are not all valid measurements; inspect each status before analysis.

| Directory | Record status | Reason / use |
|---|---|---|
| `pilot-1000-5pct-20261020/` | 3 trials failed | Retained Windows `PermissionError` failures during temporary database cleanup. Failure records are preserved. |
| `pilot-1000-5pct-20261020-retry1/` | 3 trials failed | Same cleanup failure; preserved as a separate attempt. |
| `pilot-1000-5pct-20261020-retained/` | 3 executions completed, output INVALID for analysis | Early retry retained SQLite directories to avoid cleanup failure, but serialized a verbose `SyncResult` and had incorrectly labeled summary units. Kept for provenance; do not use as a data source. |
| `pilot-1000-5pct-20261020-final1/` | 3 trials SUCCESS; exploratory diagnostic only | Compact outcome records, explicit units, JSON/CSV consistency checked. Shows the equal-assignment additive-oracle mismatch; not confirmatory and not a fair end-to-end performance comparison. |
| `pilot-1000-5pct-20261020-source-recorded/` | 3 trials SUCCESS; same-seed reproduction of `final1` | Repeated the same three workload seeds in a distinct run, captured Git/source fingerprints, and reproduced the same values, digests, SCRs, and mismatch counts. This is reproducibility evidence, not three additional independent workloads. |
| `equal-contribution-diagnostic-20261020/` | Engine-level characterization fixture | Minimal SQLite files used to inspect the `100 -> 110` equal-assignment case; not a benchmark run. |
| `increment-pilot-1000-5pct-20261020/` | 3 trials completed; preliminary, not used for provenance-sensitive analysis | Explicit `INCREMENT` pilot results retained before own-runner fingerprint/caveat metadata was finalized; not combined with the source-recorded retry. |
| `increment-pilot-1000-5pct-20261020-source-recorded/` | 3 trials SUCCESS; earlier source-recorded attempt | Same three seeds as the final pilot; preserved. Its CSV reports zero LWW write samples because telemetry was not yet balanced across systems. Do not pool it with the final run for timing analysis. |
| `increment-pilot-1000-5pct-20261020-final/` | 3 trials SUCCESS; exploratory diagnostic | Final operation-model pilot with balanced per-write and batch-sync timing boundaries, three distinct seeds, per-trial digests/order/timestamps, source revision and runner/core source hashes. JSON/CSV values and paired delta were independently rechecked. One cell only; not confirmatory. |
| `increment-pilot-1000-5pct-20261020-10-seeds/` | 10 trials SUCCESS; exploratory diagnostic | Seeds 20261100–20261109, independent traces, fresh databases, balanced system order. JSON/CSV records and retained SQLite databases passed validation. Source/environment fingerprints match the earlier final three-seed pilot. |
| `derived/increment-pilot-1000-5pct-13-independent-seeds-20261020/` | 13-trial pooled descriptive summary | Derived from the final three-seed and ten-seed raw runs after validating both and confirming matching configuration, source hashes, environment, metric definitions, unique seeds, and unique digests. Not a new measurement. |
| `increment-matrix-20261020/1000-20pct/` | 10 trials SUCCESS; exploratory diagnostic | Seeds 20261200–20261209; independent traces, fresh databases, alternating 4/3/3 system order. JSON/CSV and retained databases passed validation. Direct-SQL deltas are diagnostic only. |
| `increment-matrix-20261020/1000-50pct/` | 10 trials SUCCESS; exploratory diagnostic | Seeds 20261300–20261309; independent traces, fresh databases, alternating 4/3/3 system order. JSON/CSV and retained databases passed validation. Direct-SQL deltas are diagnostic only. |
| `derived/increment-matrix-20261020/1000-20pct/` and `1000-50pct/` | Two single-run descriptive summaries | Generated from each validated ten-trial record; not new measurements and not pooled across densities. Include medians, inclusive IQR, sample SD, range, SCR/RVAR, and order counts. |
| `increment-runtime-pilot-20261020/` | Two validated single-trial runtime pilots | 5,000/20% (seed 20261030) and 10,000/20% (seed 20261031), used only to estimate runtime. Each JSON/CSV pair and retained databases passed the increment artifact validator. One trial per cell; not empirical comparative results. Do not pool with the 1,000-row pilot. |

Validate the preserved increment pilot without rerunning it:

```powershell
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/increment_evaluation_1000_5pct.json
```

The ten-seed run was executed with:

```powershell
py -3.14 -m research.experiments.increment_evaluation --operations 1000 --density 0.05 --trials 10 --seed 20261100 --output-dir research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds
```

It completed 10 successful trials (seeds 20261100–20261109). Do not rerun into this existing directory; choose a new output path for a new experiment.

The later 1,000-operation/20% and 50% cells were executed locally with:

```powershell
py -3.14 -m research.experiments.increment_evaluation --operations 1000 --density 0.20 --trials 10 --seed 20261200 --output-dir research/experiments/runs/increment-matrix-20261020/1000-20pct
py -3.14 -m research.experiments.increment_evaluation --operations 1000 --density 0.50 --trials 10 --seed 20261300 --output-dir research/experiments/runs/increment-matrix-20261020/1000-50pct
```

Each completed 10 successful trials. Generate descriptive summaries in fresh output directories with:

```powershell
py -3.14 -m research.experiments.summarize_increment_runs --output-dir research/experiments/derived/increment-matrix-20261020/1000-20pct research/experiments/runs/increment-matrix-20261020/1000-20pct/increment_evaluation_1000_20pct.json
py -3.14 -m research.experiments.summarize_increment_runs --output-dir research/experiments/derived/increment-matrix-20261020/1000-50pct research/experiments/runs/increment-matrix-20261020/1000-50pct/increment_evaluation_1000_50pct.json
```

Summaries remain per-density, despite compatible relevant source fingerprints, and are not pooled across configurations. The direct-SQL baseline omits system guarantees, so paired deltas are not end-to-end overhead.

Validate those two raw JSON/CSV records and retained databases with:

```powershell
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-matrix-20261020/1000-20pct/increment_evaluation_1000_20pct.json
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-matrix-20261020/1000-50pct/increment_evaluation_1000_50pct.json
```

This checks saved records and retained replica databases. It is artifact validation, not experiment reproduction.

Regenerate the pooled 13-seed summary without rerunning trials:

```powershell
py -3.14 -m research.experiments.summarize_increment_runs --output-dir research/experiments/derived/increment-pilot-1000-5pct-13-independent-seeds-20261020 research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/increment_evaluation_1000_5pct.json
```

The derived output directory must not already exist. The summarizer validates every input record and requires identical configuration, source fingerprint, environment, and metric definitions; it rejects duplicate seeds or trace digests. This is an analysis command, not experiment reproduction.

Validate the two runtime-feasibility records:

```powershell
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-runtime-pilot-20261020/5000-20pct/increment_evaluation_5000_20pct.json
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-runtime-pilot-20261020/10000-20pct/increment_evaluation_10000_20pct.json
```

The single-trial runs were generated with these commands (shown for provenance; rerunning creates new measurements and should use a new output directory):

```powershell
py -3.14 -m research.experiments.increment_evaluation --operations 5000 --density 0.20 --trials 1 --seed 20261030 --output-dir research/experiments/runs/increment-runtime-pilot-20261020/5000-20pct
py -3.14 -m research.experiments.increment_evaluation --operations 10000 --density 0.20 --trials 1 --seed 20261031 --output-dir research/experiments/runs/increment-runtime-pilot-20261020/10000-20pct
```

No failed or invalid attempt was deleted, overwritten, or used to replace another run. The successful `final1` results are also not a replacement for the repository's saved nine-configuration stress matrix.
