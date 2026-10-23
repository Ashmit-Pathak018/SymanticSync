# Experimental Results and Artifact Provenance

## Definitions and scope

- **SCR:** conflict-row correctness against the generated additive oracle, scoring both replicas. It is specific to additive semantics.
- **RVAR:** agreement of ordered `bench_rows.value` values only. It does not compare full database state.
- **VRA:** unmeasured.
- Historical stress workload: sequential tracked writes followed by one pairwise batch synchronization, with two trials per configuration and seed 42 reused within each configuration.
- Explicit-INCREMENT pilot: separate workload family, two replicas, sequential writes followed by batch sync. It must not be merged with the historical SET artifacts.

## Historical SET-based matrix

The nine JSON/CSV pairs are stored at `artifacts/benchmarks/repeated-stress-20261014/`. The validator reported nine configurations, 18 artifacts, and 18 paired trials. Values below are the per-trial records; no averaging is used to hide timing variability. Times are milliseconds. `SUM SCR` and `LWW SCR` are each shown as two observations; RVAR was 100% in both trials for every configuration.

| Operations | Conflict density | Conflict rows | SUM SCR (%) | LWW SCR (%) | LWW batch sync, trials 1/2 (ms) | SUM batch sync, trials 1/2 (ms) |
|---:|---:|---:|---|---|---|---|
| 1,000 | 5% | 50 | 98.00 / 98.00 | 0 / 0 | 1,126.8 / 1,090.7 | 1,143.1 / 1,120.0 |
| 1,000 | 20% | 200 | 97.50 / 97.50 | 0 / 0 | 3,333.1 / 3,537.0 | 3,334.7 / 3,391.8 |
| 1,000 | 50% | 500 | 98.20 / 98.20 | 0 / 0 | 7,846.9 / 7,915.1 | 7,781.8 / 7,765.7 |
| 5,000 | 5% | 250 | 98.00 / 98.00 | 0 / 0 | 11,354.1 / 11,335.2 | 11,451.1 / 11,228.2 |
| 5,000 | 20% | 1,000 | 98.00 / 98.00 | 0 / 0 | 25,043.6 / 33,384.4 | 30,885.0 / 33,152.5 |
| 5,000 | 50% | 2,500 | 98.16 / 98.16 | 0 / 0 | 70,128.3 / 78,231.4 | 72,762.7 / 78,440.3 |
| 10,000 | 5% | 500 | 98.20 / 98.20 | 0 / 0 | 73,793.0 / 78,646.4 | 73,057.8 / 76,593.0 |
| 10,000 | 20% | 2,000 | 98.25 / 98.25 | 0 / 0 | 139,079.8 / 98,275.6 | 143,626.6 / 151,664.0 |
| 10,000 | 50% | 5,000 | 97.70 / 97.70 | 0 / 0 | 194,723.5 / 192,004.2 | 184,699.3 / 191,476.2 |

For this historical generation, both replicas receive absolute assignments while the oracle treats generated deltas as independent additive contributions. Equal-valued assignments are not detected as state-diff conflicts, causing the observed SUM mismatches. LWW's 0% is the result of scoring its winner-selection semantics against that additive oracle. Neither score establishes a general system ranking. The two timings per cell reuse one workload seed and show large variability in some cells; they are descriptive only.

## Explicit-INCREMENT pilot: 1,000 operations / 5% conflicts

Thirteen independent seeds (20261023–20261025 and 20261100–20261109) were pooled only after the source hashes, runtime environment, configuration, and metric definitions matched. Each seed uses fresh state and a unique workload digest. The trial execution orders occur 5, 4, and 4 times across the three rotations. Every trial completed successfully. Raw data are in `research/experiments/runs/increment-pilot-1000-5pct-20261020-final/` and `research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/`; validated derived JSON/CSV are under `research/experiments/derived/increment-pilot-1000-5pct-13-independent-seeds-20261020/`.

| System / statistic | Batch-sync median (ms) | Inclusive IQR (ms) | Range (ms) |
|---|---:|---:|---:|
| Direct application SUM | 7.992 | 7.888–8.350 | 7.628–9.785 |
| SemanticSync INCREMENT | 417.609 | 416.099–433.434 | 397.742–458.515 |
| SemanticSync LWW | 830.910 | 822.643–874.098 | 813.109–935.184 |
| INCREMENT minus direct SUM paired diagnostic | 409.585 | 406.599–424.612 | 389.840–450.654 |

The paired diagnostic mean is 415.805 ms, sample SD 17.625 ms (`n=13`). All explicit-INCREMENT and application-SUM trials had 100% SCR under the specified oracle; LWW had 0%; all had 100% RVAR. This is one configuration and no significance test is performed. The direct SQL implementation lacks durable operation receipts, conflict history, quarantine, and checkpoint behavior. Its timing cannot support a fair end-to-end overhead conclusion.

## Additional explicit-INCREMENT pilots: 1,000 operations / 20% and 50%

Two further cells completed 10 independent trials each. Their raw JSON/CSV and retained databases are under `research/experiments/runs/increment-matrix-20261020/`; validated single-run descriptive JSON/CSV are under `research/experiments/derived/increment-matrix-20261020/`. Seeds were 20261200–20261209 at 20% and 20261300–20261309 at 50%; execution order was balanced 4/3/3 across three rotations. Values are milliseconds. The `increment - direct SUM` delta is a diagnostic microbaseline difference, not end-to-end overhead.

| Density | System / statistic | Sync median | Inclusive IQR | Range |
|---|---|---:|---:|---:|
| 20% | Direct application SUM | 8.204 | 8.105–8.308 | 7.605–8.515 |
| 20% | SemanticSync INCREMENT | 601.720 | 596.006–614.755 | 583.002–634.323 |
| 20% | SemanticSync LWW | 2,204.093 | 2,190.341–2,234.331 | 2,116.198–2,252.770 |
| 20% | INCREMENT minus direct SUM delta | 593.698 | 588.226–606.418 | 574.834–626.082 |
| 50% | Direct application SUM | 8.058 | 7.970–8.186 | 7.558–8.609 |
| 50% | SemanticSync INCREMENT | 986.072 | 975.164–996.417 | 958.648–1,004.061 |
| 50% | SemanticSync LWW | 5,063.829 | 4,966.048–5,113.147 | 4,898.072–5,140.352 |
| 50% | INCREMENT minus direct SUM delta | 978.042 | 966.955–988.116 | 951.090–996.021 |

Paired-delta means/sample SDs were 597.506/14.919 ms at 20% and 977.228/14.867 ms at 50% (`n=10` each). Every explicit-INCREMENT and direct-SUM trial scored 100% conflict SCR and 100% RVAR; every LWW trial scored 0% SCR and 100% RVAR under the additive oracle. These are exploratory results for sequential tracked writes followed by batch sync. They do not establish statistical significance, an end-to-end performance advantage, or correctness beyond these generated two-replica schedules. The remaining six 5k/10k cells are unmeasured.

## Runtime-feasibility checks

Separate one-trial runs at 5k/20% and 10k/20% were executed only to estimate cost. Total durations were 90.113 s and 226.433 s. Engine-INCREMENT batch sync took 12,018.952 ms and 47,491.097 ms, respectively. These are single observations and are not samples for the 1k study or a scaling law. The artifacts remain separate under `research/experiments/runs/increment-runtime-pilot-20261020/`.

## Reproduction and interpretation

Run `py -3.14 -m backend.workloads.validate_repeated_benchmark_artifacts` to validate the historical matrix without rerunning it. Run `py -3.14 -m research.experiments.validate_increment_evaluation <path-to-json>` for each explicit-INCREMENT raw record. The pooled summary command and exact inputs are in `research/experiments/runs/README.md`.

These results do not establish concurrent-writer behavior, full-database convergence, general N-way convergence, VRA, statistical significance, or a general performance advantage. They are not the results of a fair end-to-end baseline comparison.
