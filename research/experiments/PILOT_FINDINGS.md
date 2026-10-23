# Exploratory Pilot and Oracle Boundary

**Captured:** 2026-10-20. This is diagnostic evidence, not a confirmatory study and not part of the manuscript's empirical result set.

## Reanalysis of the saved repeated matrix

Command executed from the repository root:

```powershell
py -3.14 -m research.experiments.audit_equal_assignment_mismatches
```

The read-only analysis independently recomputes each trial's SCR from its saved operations and both observed replica vectors. It verifies that every saved SemanticSync mismatch falls on a conflict-labeled row where the two generated assignments are equal.

| Operations / density | Conflict instances across 2 trials | Equal assignments across 2 trials | Mismatching conflict rows across 2 trials | Saved SCR |
|---|---:|---:|---:|---:|
| 1,000 / 5% | 100 | 2 | 2 | 98.00% |
| 1,000 / 20% | 400 | 10 | 10 | 97.50% |
| 1,000 / 50% | 1,000 | 18 | 18 | 98.20% |
| 5,000 / 5% | 500 | 10 | 10 | 98.00% |
| 5,000 / 20% | 2,000 | 40 | 40 | 98.00% |
| 5,000 / 50% | 5,000 | 92 | 92 | 98.16% |
| 10,000 / 5% | 1,000 | 18 | 18 | 98.20% |
| 10,000 / 20% | 4,000 | 70 | 70 | 98.25% |
| 10,000 / 50% | 10,000 | 230 | 230 | 97.70% |

The repeated trials in each cell use the same seed-42 trace. Here the equal-assignment and mismatch counts aggregate the two repeated executions, not independent generated workloads. The artifact values remain unchanged.

## Three-seed engine pilot

Executed command:

```powershell
py -3.14 -m research.experiments.engine_evaluation --operations 1000 --density 0.05 --trials 3 --seed 20261020 --output-dir research/experiments/runs/pilot-1000-5pct-20261020-final1
```

Raw JSON and CSV are in `research/experiments/runs/pilot-1000-5pct-20261020-final1/`; the trial SQLite directories are retained alongside them. The run used three distinct seeds and digests, balanced system order, 1,000 rows, and 5% generated conflicts. System writes were sequential, followed by a batch sync. Environment metadata in the JSON records Windows 11, Python 3.14.3, SQLite 3.50.4, DELETE journal mode, and foreign keys enabled for each connection; storage medium, memory, and host load were not measured.

The `final1` raw JSON predates source-snapshot instrumentation, so it has no run-captured Git revision or relevant source hashes. The current runner records these fields for subsequent runs; they are not retroactively inserted into `final1`.

After adding source-snapshot instrumentation, the same command was repeated with output directory `research/experiments/runs/pilot-1000-5pct-20261020-source-recorded/`. It recorded Git revision `5e98f43c972410f3403d06a27bd4bb4620a762a2`, a dirty-worktree flag, and five relevant source hashes. The same three seeds produced the same trace digests, engine SUM SCR values (100%, 98%, 96%), and mismatch counts (0, 1, 2). Its timing observations differ from `final1` and are not pooled with them; these repeats reuse the same seed set and do not add independent workload samples.

| Trial | Seed | Order | Engine SUM SCR | Engine SUM RVAR | Direct additive merge sync (ms) | Engine SUM sync (ms) | Engine SUM minus direct (ms) |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 20261020 | Direct, SUM, LWW | 100% | 100% | 12.143 | 1,043.499 | +1,031.355 |
| 2 | 20261021 | SUM, LWW, Direct | 98% | 100% | 8.848 | 1,137.866 | +1,129.018 |
| 3 | 20261022 | LWW, Direct, SUM | 96% | 100% | 8.096 | 981.493 | +973.396 |

For seeds 20261021 and 20261022, respectively one and two generated conflict rows had equal values on both replicas. The engine reported 49 and 48 conflicts (out of 50 marked rows) and left those rows at the single assigned value. The additive oracle expected each equal assignment to count twice (for example, base 100 with both replicas at 110 gives 120), which is not inferable from replacement values alone unless operation intent is modeled. An engine-level test preserves this counterexample at `backend/tests/test_research_evaluation.py::test_equal_concurrent_assignments_are_a_counterexample_for_additive_intent`.

The application baseline implements the additive equation with direct SQL and does not provide SemanticSync's operation identity, replay receipts, conflict persistence, quarantine, or checkpoint guarantees. Its timing is therefore not a fair end-to-end baseline; paired differences are reported only as raw pilot diagnostics. The additive-oracle mismatch must be resolved or the workload semantics explicitly revised and predeclared before a confirmatory correctness or performance study. LWW remains an oracle-specific policy contrast, not a general CRDT baseline.

## Explicit `INCREMENT` operation pilot (2026-10-20)

After adding a distinct tracked `INCREMENT` operation, a new exploratory 1,000-row, 5%-conflict-density run executed three independent seeds (20261023–20261025), each on fresh replica databases. The final source-fingerprinted trial records and databases are in `runs/increment-pilot-1000-5pct-20261020-final/`. The JSON captures source revision/dirty status, relevant file hashes (including the runner), platform/runtime metadata, trace digest, execution order, per-system values, and trial timestamps. Earlier pilot folders are preserved and are not pooled with this run.

The independent check is now reproducible with `py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json`. It recomputes all three trace digests and conflict-row values, validates JSON/CSV records and summaries, checks source-hash presence and SQLite integrity, and confirms exactly 1,050 unique increment receipts on each replica in every trial. All trials were `SUCCESS`; explicit engine `INCREMENT` and the direct application SUM implementation each scored 100% conflict SCR, while LWW scored 0% under this additive oracle. The paired engine-increment-minus-application-SUM batch-sync deltas were +406.599 ms, +441.477 ms, and +424.612 ms (median +424.612 ms, range +406.599 to +441.477 ms). The application path uses a narrow direct SQL additive merge and lacks equivalent operation receipts, conflict persistence, quarantine, and checkpoint safety. These times therefore describe mechanism cost under one small workload only; they do not establish equivalent-guarantee overhead, statistical significance, or a general performance advantage. The LWW score is a semantic contrast, not a comparable timing baseline.

The original pilot covered one workload configuration and three seeds, not the planned matrix or ten-seed target. The workload remains sequential tracked writes followed by one batch sync. No full-database convergence, concurrent-writer, N-way, or general convergence claim follows.

## Pooled independent-seed 1k/5% pilot

A later ten-trial run added seeds 20261100–20261109. Its relevant source hashes, Git revision, runtime environment, workload configuration, metric definitions, and execution protocol exactly match the earlier three-trial `increment-pilot-1000-5pct-20261020-final/` record; the 13 seeds and trace digests are all unique. The raw runs remain separate. They are combined only by the validation-first analysis command below, which rejects mismatched provenance, repeated seeds, or repeated digests:

```powershell
py -3.14 -m research.experiments.summarize_increment_runs --output-dir research/experiments/derived/increment-pilot-1000-5pct-13-independent-seeds-20261020 research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/increment_evaluation_1000_5pct.json
```

It validates both JSON/CSV records and retained replica databases before pooling, then writes derived JSON/CSV under `research/experiments/derived/increment-pilot-1000-5pct-13-independent-seeds-20261020/`. The 13-trial execution orders were balanced across the three rotations (5, 4, and 4 trials); every trial completed successfully. IQR uses inclusive sample quartiles (`statistics.quantiles(..., method="inclusive")`).

| System / comparison | Batch-sync median (ms) | IQR (ms) | Range (ms) |
|---|---:|---:|---:|
| Direct application SUM | 7.992 | 7.888–8.350 | 7.628–9.785 |
| SemanticSync INCREMENT | 417.609 | 416.099–433.434 | 397.742–458.515 |
| SemanticSync LWW | 830.910 | 822.643–874.098 | 813.109–935.184 |
| INCREMENT minus direct SUM paired delta | 409.585 | 406.599–424.612 | 389.840–450.654 |

The paired-delta mean was 415.805 ms with sample standard deviation 17.625 ms (`n=13`). These are descriptive statistics, not a significance test. The direct SQL SUM path omits receipts, durable operation identity, conflict persistence, FK quarantine, and checkpoint behavior, so the delta is not an end-to-end overhead comparison. All 13 explicit-INCREMENT and direct-SUM trials scored 100% SCR against this generated additive oracle; LWW scored 0% under that oracle; all three strategies had 100% benchmark-row value agreement. This one 1k/5% configuration cannot establish general correctness, convergence, superiority, or a performance advantage. VRA remains unmeasured.

This 13-trial sample addresses only the initial exploratory target for one cell. It does not supply ten trials for the other eight configurations and is not a confirmatory study.

## Additional explicit-INCREMENT density cells (2026-10-20)

Ten additional independent trials were executed for each remaining 1,000-operation density using fresh SQLite state, distinct seeds, and the same generated contribution model. The saved artifacts and retained databases are under `runs/increment-matrix-20261020/`; each JSON/CSV pair passed `validate_increment_evaluation`. The summarizer generated one descriptive JSON/CSV pair per density under `research/experiments/derived/increment-matrix-20261020/`. Order counts were 4/3/3 across the three rotations for both cells. No trial was omitted.

| Density | Trials / seeds | Application SUM sync median [IQR] (ms) | Explicit INCREMENT sync median [IQR] (ms) | LWW sync median [IQR] (ms) | INCREMENT minus direct SUM paired delta: median [IQR], range (ms) |
|---|---|---:|---:|---:|---:|
| 20% | 10 / 20261200–20261209 | 8.204 [8.105–8.308] | 601.720 [596.006–614.755] | 2,204.093 [2,190.341–2,234.331] | 593.698 [588.226–606.418], 574.834–626.082 |
| 50% | 10 / 20261300–20261309 | 8.058 [7.970–8.186] | 986.072 [975.164–996.417] | 5,063.829 [4,966.048–5,113.147] | 978.042 [966.955–988.116], 951.090–996.021 |

The paired-delta means and sample standard deviations were 597.506 ms / 14.919 ms at 20%, and 977.228 ms / 14.867 ms at 50% (`n=10` each). All 20 explicit-INCREMENT and direct-SUM trials had 100% conflict SCR and 100% RVAR; LWW had 0% conflict SCR and 100% RVAR under the additive oracle. These are oracle-specific outcomes for sequential tracked writes followed by batch sync. The direct-SQL SUM baseline lacks operation identity, receipts, conflict persistence, quarantine, and checkpoint behavior, so these deltas are not end-to-end overhead comparisons. These cells do not resolve the six missing 5k/10k density configurations, establish statistical significance, or support a general performance claim.

## Runtime-feasibility scale pilots (2026-10-20)

Two additional one-trial runs estimate execution cost only. They are not pooled with the 1,000-row pilot, are not inferential samples, and do not establish a performance comparison. Each ran on fresh databases with sequential writes followed by batch synchronization. The paired delta below is the recorded engine-INCREMENT batch-sync duration minus the direct application-SUM batch-sync duration; the direct SQL implementation does not provide equivalent replication guarantees.

| Configuration | Seed | Trial duration | Application SUM batch sync | Engine INCREMENT batch sync | Engine LWW batch sync | Paired diagnostic delta |
|---|---:|---:|---:|---:|---:|---:|
| 5,000 operations / 20% | 20261030 | 90.113 s | 21.390 ms | 12,018.952 ms | 21,687.998 ms | +11,997.562 ms |
| 10,000 operations / 20% | 20261031 | 226.433 s | 33.692 ms | 47,491.097 ms | 62,375.166 ms | +47,457.404 ms |

The 10,000-operation configuration took about 2.51 times as long as the 5,000-operation configuration in these single observations, but this ratio is descriptive only and can reflect workload details, implementation costs, and machine state. The increment engine's 5,000- and 10,000-operation synchronization durations were approximately 12.0 s and 47.5 s; this scaling and high cost should be investigated before planning a large repeated matrix. No trial was dropped. Both records were validated with `validate_increment_evaluation`; the saved JSON/CSV and retained SQLite databases are under `research/experiments/runs/increment-runtime-pilot-20261020/`. The 10,000-operation trace digest is `01ea66a4743a8b50772db7ef5b2fe256768073611010123e7b6f8a0ba32e5b31`; the 5,000-operation digest is `df78f4e2a7ad71d471788b2b1b6a313b1b6d760d20a22ee8f957b7d8bfe2ffd6`.

The 10,000-operation run scored 100% conflict SCR for direct SUM and explicit INCREMENT, 0% for LWW under the additive oracle, and 100% benchmark-row value agreement for all three. These outcomes characterize this generated workload and its oracle, not general superiority or convergence. The files are runtime-estimation artifacts, not manuscript empirical results.
