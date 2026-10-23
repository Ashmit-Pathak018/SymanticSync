# Workload Specification

## Existing synthetic stress workload

Source: `backend/workloads/stress_harness.py`.

| Element | Current behavior |
|---|---|
| Schema | `bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)` |
| Base | Every row starts at integer 100 in a freshly created base database for each system/trial. |
| Size | 1,000, 5,000, or 10,000 rows/operations. |
| Conflict count | `round(n * density)` rows; densities are 5%, 20%, or 50%. |
| Updates | Replica A receives `100 + delta_a`; conflict rows also receive `100 + delta_b` on B. Each delta is generated independently as an integer from 1 to 50. Non-conflict rows have only A's change. |
| Trace | A deterministic `random.Random(seed)` generates deltas, then shuffles the operation records. Each trial pair receives the same operation list. |
| Systems | Baseline sync uses LWW; SemanticSync uses SUM. Each gets an equivalent fresh database image and the same trace. |
| Schedule | The loop invokes tracked writes sequentially, then calls one pairwise `sync_replicas`; this is not simultaneous concurrency. |
| Order | Execution order alternates by trial index (baseline first, then SemanticSync first). |
| Persisted observation | Values are read from `bench_rows` ordered by `id`; receipt counts are read from `_ss_change_log`. |

**Operation-intent boundary:** The historical runner uses absolute `SET` operations through `apply_change`; the additive oracle interprets generated deltas as independent contributions. Equal-valued assignments therefore remain an identified mismatch in that historical workload. The engine now has a separate tracked `apply_increment` / `INCREMENT` operation that records a delta and stable operation ID. A separate explicit-INCREMENT pilot covers 13 independent seeds for 1,000 operations / 5% density. Raw runs and the validated pooled summary are stored at `research/experiments/runs/increment-pilot-1000-5pct-20261020-final/`, `research/experiments/runs/increment-pilot-1000-5pct-20261020-10-seeds/`, and `research/experiments/derived/increment-pilot-1000-5pct-13-independent-seeds-20261020/`. It does not overwrite or relabel the historical matrix, cover the full matrix, or establish general performance or convergence claims.

## Separate explicit-INCREMENT pilot

This pilot is not part of the nine-cell SET-based stress matrix.

| Element | Current behavior |
|---|---|
| Schema/base | `bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)`; base value 100; fresh databases per system and trial. |
| Trials | 13 independent seeds for 1,000 operations / 5% density; one measurement per seed; each paired system uses the same generated operation trace. |
| Operation model | Replica A receives an explicit tracked `INCREMENT(delta_a)` for every generated row; replica B receives `INCREMENT(delta_b)` only for generated conflict rows. The operation carries a stable ID and source metadata. |
| Systems | SemanticSync engine `INCREMENT`; direct application-level SQL additive merge; engine `SET` + LWW as an oracle-specific semantic contrast. |
| Schedule | Sequential local writes followed by one pairwise batch synchronization; no simultaneous writers or network contention. |
| Timing | Per-write call samples and a batch-sync interval. The recorded paired delta is engine INCREMENT batch sync minus direct-SQL SUM batch sync. The direct path lacks equivalent receipts, conflict persistence, quarantine, and checkpoint behavior, so this delta is diagnostic rather than a fair end-to-end overhead estimate. |
| Provenance | Captured Python/OS/SQLite and engine settings; the 13-seed runs have matching source snapshots and environment records. Storage medium, physical memory, and host load were not measured. |

One-trial 5k/20% and 10k/20% scale runs estimate runtime only; they are not additional samples in the 1k/5% study. See `PILOT_FINDINGS.md` and `runs/README.md` for exact outcomes and commands.

### Oracle and metric eligibility

For a conflict row, the additive expected value is `100 + delta_a + delta_b`. For a non-conflict row, the expected value is `100 + delta_a`. The stress harness SCR excludes non-conflict rows and scores both replicas for each conflict row, so the denominator is `2 * conflict_count`; with zero conflicts, SCR is null. An independent test oracle should compute expected values from the generated base and deltas without calling `calculate_quality_metrics`, `SemanticResolver`, or a helper shared with the harness.

LWW selects one side under its configured timestamp/tie-break behavior. Since the selected SCR oracle requires both contributions to be present, LWW's result is not expected to match the additive oracle. That result describes this workload/oracle pair; it does not establish that SUM is generally superior or that LWW violates its own semantics.

RVAR compares only the ordered `bench_rows.value` projections between replicas. It omits schema, other tables, operation logs, receipts, quarantine, ACKs, and checkpoint state. VRA is undefined for this synthetic schema/workload and remains unmeasured. Neither RVAR nor SCR is full-database convergence.

## Proposed independent-seed extension

For future runs, define one trial as one independently seeded operation trace and one fresh paired execution of both systems. Record `(configuration_id, trial_id, seed, workload_digest, execution_order, system, outcome)` for every trial. The pair must use the exact same operations and equivalent initial state; different pairs should use different seeds. Retain failure outcomes and logs. Do not call multiple replays of seed 42 independent workload trials.

## Coverage not supplied by this workload

- Concurrent writes, lock contention, or network delay.
- Three- or five-replica performance. Separate N-replica correctness tests cover selected schedules, not this benchmark matrix.
- Non-integer data, schema evolution, foreign-key workloads, or meaningful VRA.
- Full-database equality or general convergence.
- CPU, peak memory, storage throughput, or complete resource overhead.
