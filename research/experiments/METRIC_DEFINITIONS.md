# Metric Definitions

These definitions separate value correctness, row agreement, state convergence, and history safety. A metric is reported only when the workload observes its required state.

## SCR — conflict-row semantic correctness

For each generated conflict row `i`, the harness has predeclared additive oracle value `o_i = base_i + delta_A_i + delta_B_i`. Let `v_{r,i}` be the persisted value on replica `r`. Then:

`SCR = 100 * sum(1[v_{r,i} = o_i]) / (2 * number_of_conflict_rows)`.

Only conflict rows are in the denominator; both replicas are scored. With zero conflicts, SCR is undefined and serialized as null. In this workload, SCR is specific to the additive oracle and does not serve as a neutral score for LWW.

## RVAR — benchmark-row value agreement

`RVAR = 100 * matching ordered bench_rows.value pairs / number_of_observed benchmark rows`.

It compares only the benchmark table's value projection in row-ID order. It is not complete database state equivalence and must not be called full-database convergence. Empty-workload behavior must be specified by the invoking validator; the current harness returns 100% for zero rows.

## VRA — validation rejection accuracy

VRA requires inputs with an independently defined validity predicate and records both valid and invalid operations, expected acceptance/rejection, and actual outcome. The synthetic integer-SUM workload has no such range or relational predicate, so VRA is null/unmeasured. Do not infer it from exception counts or RVAR.

## Batch-sync duration and paired deltas

- `batch_sync_ms`: `perf_counter` wall-clock interval immediately around a single `sync_replicas(...)` call. It excludes database initialization and local writes.
- Historical SET-based stress artifact delta: SemanticSync SUM `sync_ms` minus engine LWW `sync_ms` from the same trial pair. The policies differ, and the additive oracle is asymmetric for LWW; this is a distinct-strategy timing reference, not a same-semantics overhead estimate.
- Explicit-INCREMENT pilot delta: engine `INCREMENT` batch-sync duration minus direct application-SUM merge duration from the same generated operation trace. The direct SQL path lacks equivalent operation receipts, conflict persistence, FK quarantine, and checkpoint behavior, so the paired delta is a mechanism-cost diagnostic, not a fair end-to-end comparison.
- Positive deltas mean the first named path took longer in that pair; negative values mean it took less time. Neither definition by itself supports a general performance claim.

## Tracked-write latency

Each sample is a wall-clock interval around one local mutation operation. The historical SET harness times `apply_change(...)`; the explicit-INCREMENT pilot times `apply_increment(...)` for SemanticSync and one direct SQL transaction for the application path. Calls are sequential. Percentiles and means aggregate call samples within a trial; the pooled pilot's write-p95 distribution summarizes 13 trial-level p95 values, not all raw calls pooled together.

## Operation/receipt counts

The harness currently reads `_ss_change_log` row counts from both replicas. These are row counts, not bytes, retained-history size, or general log-growth rate. A count alone does not establish replication correctness.

## Statistics and scope

The saved SET-based repeated artifacts report medians and ranges from two paired trials, reusing one workload seed per configuration. The separate explicit-INCREMENT pilot has 13 independent seeds in one 1k/5% cell; its descriptive aggregation reports median, inclusive IQR, range, mean, and sample SD. Two larger single-trial runs are runtime feasibility observations only. None of these summaries support statistical significance or a general performance advantage. Broader independent-seed trials require an explicit paired analysis plan and a semantically comparable baseline.
