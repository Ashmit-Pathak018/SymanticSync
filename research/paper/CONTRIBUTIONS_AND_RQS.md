# Contributions and Research Questions

## Bounded contribution statement

SemanticSync is a Python/SQLite prototype that combines schema-assigned field policies with tracked local mutations, operation-aware replay for explicit increments, selected conflict review and relational quarantine paths, and checkpoint-assisted log compaction. Its contribution is currently an implementation and evidence package, not a new merge algorithm or proven convergence protocol.

## Contributions supported within tested scope

1. **Separate operation intent:** absolute `SET` and explicit `INCREMENT` have different tracked semantics. Selected two-replica replay, duplicate delivery, restart, and one post-checkpoint increment case are regression-tested. Thirteen independent 1k/5% pilot traces matched the additive conflict-row oracle. This does not establish arbitrary-order or general N-replica convergence.
2. **Policy and failure characterization:** tests document selected behaviors and boundaries for SUM, BOUNDED_SUM, AVG, APPEND, LWW, REJECT, MIN, and MAX. Finite tests do not prove algebraic properties over all SQLite values or histories.
3. **Conservative relational and history handling:** selected tracked mutation paths quarantine supported dependent rows and checkpoint pruning validates multiple evidence sources. SQL-console/external-process writes, unsupported schemas, manual RESOLVE-tail review, single-process coordination, and uncertified power-loss durability remain explicit boundaries.
4. **Reproducible artifact checks:** benchmark records, operation traces, source/environment metadata, and validators are retained. Validation of saved data is distinct from rerunning the experiment.

## Research questions and status

| RQ | Question | Current answer |
|---|---|---|
| RQ1 | Can explicit operation intent avoid treating equal absolute assignments as independent increments? | **Supported for selected cases.** `INCREMENT(+10)` on both replicas from 100 reaches 120 in tests; equal `SET(110)` remains an assignment outcome rather than being reinterpreted as 120. The 13-seed 1k/5% pilot matched its predeclared additive oracle. General schedules remain unverified. |
| RQ2 | What cost does the tracked engine add relative to a comparable additive implementation? | **Unanswered.** Direct-SQL SUM shares the scalar equation but lacks receipts, conflict persistence, FK quarantine, and checkpoint guarantees. Its observed paired deltas are diagnostic only. |
| RQ3 | Which policy and relational-integrity properties hold? | **Partially answered.** Specific fixtures and schedules are covered; no proof or complete state-space exploration exists. |
| RQ4 | What checkpoint recovery and pruning boundaries are supported? | **Partially answered.** The documented Phase 6 scope is tested. RESOLVE tails require manual review; coordination is process-local; power-loss durability is not certified. |

## Claims explicitly not made

- No claim of a novel algorithm, universal policy superiority, or first system to support semantic merge policies.
- No general convergence, arbitrary-schedule correctness, concurrent-writer performance, or full-database convergence claim.
- No statistical significance or general performance advantage claim.
- No claim that direct-SQL measurements compare equal system guarantees.

See `EXPERIMENTAL_RESULTS.md`, `THREATS_TO_VALIDITY.md`, and the maintained claim register before using any claim externally.
