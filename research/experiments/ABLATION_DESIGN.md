# Ablation Design and Evidence Status

**Status:** No controlled ablation has been executed. This note records which ablations are meaningful and what would be required before interpreting their timings.

## Principle

An ablation is valid only when the compared variants execute the same declared operations and produce the same accepted/rejected outcomes and final state. Removing a safety mechanism can alter those outcomes; timing such a variant is not an equivalent-performance comparison. Keep any experimental switch in an isolated research runner or branch, never as an implicit production setting.

## Candidate ablations

| Component | Proposed contrast | Equivalence requirements | Current decision |
|---|---|---|---|
| Tracked operation validation | Full `INCREMENT` path versus a variant without complete-row readback, FK/integrity checks, or trigger-result validation | Identical accepted operations, final values, failures, operation IDs, receipts, and retry semantics | **Do not run as a performance ablation.** Removing these checks can accept mutated or ignored writes and changes safety. A microbenchmark of an isolated validation query may be useful, but cannot be reported as total system overhead. |
| Conflict detection / conflict persistence | Full sync versus no detection or no durable conflict record | Same conflict classifications, unresolved states, and replay behavior | **Do not run by disabling the component.** It changes visible system behavior and history. Instrument phase durations inside the production path first, then measure without disabling the path. |
| Operation identity / receipt deduplication | Full replay versus no receipts or ID checking | Same exactly-once materialized effects for duplicate delivery and after restart | **Invalid ablation.** Removing receipts changes semantics and can apply increments more than once. Existing duplicate/restart tests define required behavior. |
| Checkpoint and log compaction | Retain all acknowledged history versus validated checkpoint + pruning | Both variants must preserve row state, operation IDs, receipts, ACK evidence, retry behavior, and restart recovery; only retained-log size and checkpoint cost should differ | **Potentially safe and relevant, but not measured.** The comparison must use a validated committed manifest and all required replica ACKs. Report checkpoint capture, prune, recovery, retained bytes, and post-checkpoint sync separately. Do not compare a direct row copy or unvalidated pruning path. |
| Direct application merge | Application-level scalar addition versus tracked engine path | Scalar output can match, but persistence, replay, conflict, and relational guarantees are not equivalent | Already measured only as a **narrow microbaseline**. It is not a safety-component ablation or fair end-to-end baseline. See `BASELINE_DESIGN.md`. |

## Required protocol for a future checkpoint ablation

1. Generate one immutable operation trace and initialize equivalent fresh databases for each variant.
2. Run tracked writes and sync until the same causal frontier is acknowledged by the exact configured members.
3. In the compaction arm, create and validate the checkpoint, then prune only through the validated stable horizon. In the control arm, retain the acknowledged hot log without pruning.
4. Measure checkpoint capture, validation, pruning, restart/recovery, retained database/log bytes, and subsequent synchronization as separate boundaries.
5. Compare all user rows, schemas, live and compacted receipts, ACK vectors, conflict history, and replay behavior. Include duplicate delivery, restart, and injected pruning failure.
6. Use independent paired seeds, balanced order, retained raw records, and enough trials to characterize variability. A single pair is runtime feasibility only.

If the checkpoint path cannot be isolated while preserving its validation and membership requirements, report the ablation as infeasible under the current architecture rather than weakening those requirements.

## Current evidence

No ablation-specific measurements exist. The runtime-feasibility experiments in `runs/increment-runtime-pilot-20261020/` compare explicit engine increments, engine LWW, and direct application SUM; they do not remove or isolate an internal component. No ablation result is included in manuscript conclusions.
