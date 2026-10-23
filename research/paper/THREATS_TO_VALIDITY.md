# Threats to Validity

## Construct validity

The historical SET benchmark's additive oracle interprets generated value differences as independent contributions, an intent not encoded by absolute assignments. Equal values can hide multiple writes from a state-diff conflict detector. SCR is consequently specific to the defined additive workload; the 0% LWW score is not a universal correctness ranking. RVAR observes only benchmark-row values, not full database state; VRA is not measured. The separate INCREMENT pilot encodes contribution intent explicitly but covers only the 1k/5% cell with 13 seeds.

## Internal validity

The historical matrix has two measurements per configuration with a shared seed and trace. The 13-seed pilot improves seed diversity for one cell, but the direct-SQL additive path lacks equivalent operation identity, receipts, durable conflict history, FK quarantine, and checkpoint behavior. Its paired timing difference is not an end-to-end cost comparison. Runs are sequential tracked writes followed by batch synchronization; they do not measure writer contention. The environment is a Windows 11/Python 3.14.3/SQLite 3.50.4 host, with storage medium, physical memory, host load, thermal state, and power state unmeasured. Order is balanced across three rotations for the 13-seed pilot, but process-level and filesystem effects remain possible.

## External validity

The benchmark uses a synthetic integer table with a common base and two replicas. It does not represent a production schema, non-integer policies, real application workload, network delay, three-/five-replica benchmark performance, or concurrent writers. N-replica correctness tests cover selected finite topologies and schedules only. Results cannot be generalized to arbitrary relational applications or merge-policy workloads.

## Conclusion validity

The 13-seed pilot is exploratory and has no predeclared inferential hypothesis or power analysis. Its descriptive median, IQR, range, mean, and sample standard deviation do not establish statistical significance. The direct-SQL comparison is semantically narrower and cannot establish general overhead or superiority. Historical two-trial timing ranges vary substantially in some cells. No formal proof establishes policy algebra or general convergence.

## Implementation and recovery scope

Passing finite tests does not prove absence of faults across every schema, SQLite trigger, schedule, or crash point. Checkpoint coordination uses a process-local lock; direct SQL and external processes can bypass tracked operations; some schema shapes are rejected; RESOLVE-tail recovery requires manual review; cross-store atomicity and power-loss durability are not certified. Phase 6 approval remains scoped to its documented tested cases.

## Literature scope

The related-work review is selective and based on the local paper collection plus limited authoritative checks. It is not a systematic or exhaustive search. Bibliographic uncertainties and unsupported novelty claims are documented in `research/related_work/REFERENCE_VERIFICATION.md` and `research/related_work/NOVELTY_ASSESSMENT.md`.
