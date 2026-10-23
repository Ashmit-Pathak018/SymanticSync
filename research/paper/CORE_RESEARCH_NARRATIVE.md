# Core Research Narrative

## Problem

Local replicas can make independent changes while disconnected. A replacement assignment such as `SET(110)` does not reveal whether a user intended an absolute value or a contribution of `+10`; two replicas with the same final value 110 are observationally indistinguishable from the row values alone. Treating every observed difference as a contribution can therefore invent intent, while selecting one winner can discard an independent contribution when the operation was in fact additive.

## System approach

SemanticSync is a Python/FastAPI/SQLite prototype. It assigns field-level merge policies through schema metadata and retains tracked operation history. The implementation distinguishes absolute updates from an explicit signed `INCREMENT`, which carries operation identity and can be replayed with receipt-based duplicate handling. It also includes selected conflict-review, foreign-key quarantine, and checkpoint-assisted compaction workflows.

## Evidence

The key semantic example is tested: from a common value of 100, two explicit `INCREMENT(+10)` operations produce 120 in the tested two-replica flow; two absolute `SET(110)` operations are not reinterpreted as two contributions. Duplicate delivery, selected reversed delivery, restart, and a post-checkpoint increment case have regression coverage. These results concern enumerated schedules, not arbitrary histories.

The historical nine-configuration stress matrix remains SET-based, with two trials per cell and a shared seed-42 trace. Its additive oracle cannot infer equal-valued assignment intent; its LWW 0% SCR is specific to that oracle, not a neutral ranking. A new explicit-INCREMENT pilot has 13 independent seeds in only the 1k/5% cell. The direct-SQL additive path lacks SemanticSync’s replication guarantees, so its paired timing difference is not a fair end-to-end overhead measurement. RVAR compares only benchmark-row values; VRA is unmeasured.

## Contribution boundary

The defensible result is an implementation distinction between explicit contribution operations and absolute assignments, plus finite replay and recovery evidence. The existing work does not establish a new general merge algorithm, arbitrary-order N-way convergence, universal relational integrity, or performance superiority. The related-work selection is selective and cannot support an exhaustive novelty claim.

## Remaining research

The next empirical step requires a semantically comparable baseline with defined replay, persistence, and failure guarantees; followed by independent trials across the workload matrix and safe ablations. The current scale pilots indicate substantial cost at 5k/20% and 10k/20%, so matrix runtime and resource needs need planning. Primary-source verification of the closest related systems and additional state-machine testing are also required before stronger claims.
