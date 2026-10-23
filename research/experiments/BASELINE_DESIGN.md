# Baseline Design

## Existing LWW comparison

The saved benchmark compares SemanticSync's `SUM` synchronization path with an LWW synchronization path. Both receive the same generated paired trace and equivalent initial database state. This is useful for observing their behavior and timing under the specified workload, but the correctness comparison is asymmetric: the SCR oracle expects both independent additive deltas, while LWW intentionally selects one value. Therefore:

- LWW's 0% SCR is an expected consequence of the additive oracle for rows with nonzero independent deltas, subject to actual winner selection.
- The value does not show LWW is incorrect under its own policy semantics.
- The value does not show SemanticSync is generally more correct or superior.
- LWW timing is not a same-semantics baseline for measuring SUM's incremental overhead.

Keep this comparison labeled as an **oracle-specific policy contrast** and a **distinct-strategy timing reference**, not a neutral baseline or universal performance evaluation.

## Candidate same-semantics baseline

If an overhead comparison is pursued, first implement a small independent application-level additive baseline with the same domain rule `base + (A-base) + (B-base)`, schema, operation trace, equivalent fresh initial state, validation, and final observation points. Its expected values must come from a separately written oracle, not the baseline or engine helper. Report separately:

1. tracked local write path cost;
2. batch synchronization path cost;
3. baseline persistence/merge cost over identical inputs;
4. any work intentionally omitted by the application-level baseline, such as durable operation identity, replay receipts, conflict persistence, FK checks, or checkpoint behavior.

If the baseline omits those guarantees, call it a narrow scalar-merge microbaseline and do not imply architectural equivalence. A full end-to-end comparison requires equivalent failure, durability, retry, and integrity semantics, which are not currently implemented in the benchmark.

### Local three-seed pilot finding (2026-10-20)

An exploratory 1,000-row / 5% run found a workload-semantics counterexample: in trials 2 and 3, one and two marked conflict rows respectively had equal non-base values on both replicas. The additive oracle counted both writes as independent contributions, while `ConflictDetector.detect` requires unequal replica values to emit an UPDATE_UPDATE conflict. SUM therefore left those values unchanged (110 instead of 120 in trial 2; 133 instead of 166 and 113 instead of 126 in trial 3). The run's engine SUM SCR was 100%, 98%, and 96%; RVAR was 100% in all trials.

This is not evidence that either strategy is universally preferable. It showed that the historical benchmark's additive-intent model was not observable through absolute assignments and state-diff conflict detection for equal resulting values. The explicit `INCREMENT` operation was then added as a separate tracked operation. Explicit-INCREMENT pilots now cover the three 1k densities with 13, 10, and 10 independent trials respectively, all matching the additive oracle in their recorded conflict rows. Raw runs and validated descriptive summaries are retained under `research/experiments/runs/` and `research/experiments/derived/`. The historical SET artifacts were not changed. Do not use the direct-SQL additive path as a fair end-to-end baseline or these pilots as confirmatory manuscript evidence. Operation-intent behavior has been measured across the three 1k densities only; 5k/10k matrix cells and comparable end-to-end cost remain unmeasured.

## Manual conflict and REJECT

REJECT can be compared descriptively by number of flagged conflicts and unresolved rows under a defined workload. The repository has no human study or intervention-time data; do not estimate human resolution time. A future manual-resolution experiment must specify the actual UI/API workflow, payloads, audit trail, failure handling, and task protocol before collecting latency.

## CRDT/operation-based baseline

Do not present LWW as representative of CRDTs. Any CRDT baseline must name the concrete implementation/version, data type, operation metadata, merge semantics, delivery assumptions, and supported invariants. A counter CRDT can be comparable to additive counters only when its observed semantics and failure assumptions are aligned; generic claims require source-level justification. No comparable CRDT performance baseline is present in the saved artifacts.

## Comparison status matrix

| Approach | Semantic match to explicit increment | Workload/oracle | Costs and behavior available | Guarantees / limitations | Evidence status |
|---|---|---|---|---|---|
| SemanticSync `INCREMENT` | Subject under study; explicit signed increment operations | Same generated increment trace; conflict-row additive oracle; two replicas; sequential tracked writes then batch sync | Tracked-write samples, batch-sync duration, SCR, RVAR, receipts | Operation identity, conditional replay, and integrity checks exist on the exercised path; finite schedules only | Empirical exploratory pilots at 1k/5%, 1k/20%, and 1k/50% with 13/10/10 independent seeds; one trial each at 5k/20% and 10k/20%; six 5k/10k cells remain unmeasured |
| Engine LWW | No for additive-preservation correctness; useful policy contrast | Same paired trace and initial state; additive SCR is intentionally asymmetric for LWW | Batch-sync time, SCR, benchmark-row value agreement | Selects a winner; does not preserve both independent additive contributions; timestamp ordering is not causality | Empirical behavior observed; timing not a fair SUM/INCREMENT overhead baseline |
| Direct-SQL application SUM | Matches the scalar additive equation on the generated workload | Same trace/base and independent additive oracle | Write and merge/sync time, final benchmark values | Does not implement durable operation IDs, replay receipts, conflict history, FK quarantine, or checkpoint recovery | Empirical narrow microbaseline; not end-to-end comparable |
| `REJECT` / manual review | Different policy; compatible only for conflict-count burden | Could reuse generated conflict rows; outcome is unresolved rather than materialized additive value | Conflict counts and unresolved rows can be counted | No human resolution-time or user-study evidence | Behavior has regression coverage; benchmark comparison not run |
| External operation-based counter / CRDT | Potentially comparable only if operation model, constraints, and delivery assumptions align | No concrete version/configuration selected | None | Must name exact implementation, data type, metadata, and guarantees before comparison | No empirical comparison; remains a research design item |

The pilot's raw records are retained under `research/experiments/runs/`. In particular, the 5k and 10k runtime-feasibility trials use only one sample each, and the direct-SQL sync path omits system guarantees. Their paired deltas are reported as diagnostics and must not be called SemanticSync overhead or a performance disadvantage.

## Fairness requirements before new measurement

- Predeclare workload and oracle; use independent seeds between paired trials.
- Run both systems from equivalent fresh bases and retain every attempted trial.
- Balance execution order; capture environment metadata.
- Report only metrics with matching measurement boundaries.
- Validate raw records and derive tables/plots automatically.
- Avoid significance or advantage claims until sample-size assumptions and a defensible same-semantics comparison are established.
