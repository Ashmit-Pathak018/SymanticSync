# Experimental Protocol

**Status:** Exploratory assignment-based, explicit-INCREMENT, and runtime-feasibility pilots executed 2026-10-20; explicit-INCREMENT trials cover all three densities at 1,000 operations (13/10/10 independent seeds). The protocol remains unapproved for confirmatory measurement.
**Scope:** Evidence that can be measured by the current SemanticSync engine and a bounded set of future comparisons.

## Research questions

### RQ1 — What correctness does the current two-replica SUM workload demonstrate?

- **Hypothesis:** Not yet accepted. A three-seed assignment-based pilot exposed that equal-valued `SET`s are counted as two contributions by the historical oracle but are not detected as a conflict by the state-diff engine. The implementation now offers a separate tracked `INCREMENT` operation for explicit contribution intent. Thirteen independent 1k/5% trials using `INCREMENT` matched the additive oracle in that cell. This does not retroactively validate the historical `SET`-based artifacts or establish correctness across the workload matrix.
- **Independent variables:** operation count (1k, 5k, 10k), conflict density (5%, 20%, 50%), and independent workload seed.
- **Dependent variables:** conflict-only SCR on both replicas; benchmark-row value agreement (RVAR); rejected/failed operation counts if captured.
- **Controlled:** schema, base value, delta range, paired operation trace, runtime/configuration, trial reset, and sync boundary.
- **Baseline:** LWW is descriptive only for this additive oracle; it is not a semantically equivalent correctness baseline. A future same-semantics baseline must implement the same base-relative additive rule independently and be checked against a separately written oracle.
- **Acceptance evidence:** all planned trial outcomes and raw values retained; oracle defined before execution; each trial validates exact expected values and receipt/status outcomes. The historical assignment-based pilot does not meet this criterion for equal-valued assignment rows. Explicit `INCREMENT` pilots completed with 13 independent seeds at 1k/5% and 10 each at 1k/20% and 1k/50%, all with SCR 100% for the generated additive workload. These are exploratory; the 5k and 10k sizes remain incomplete.
- **Threats:** two replicas only; sequential writes; trigger/SQLite behavior; same machine and load; limited integer-only schema.

### RQ2 — What costs are associated with the tracked-write and batch-sync paths?

- **Hypothesis:** Exploratory only until a comparable baseline and stable trial distribution are established.
- **Independent variables:** workload size, conflict density, and paired implementation order.
- **Dependent variables:** per-call tracked-write p50/p95/p99 and mean; batch `sync_replicas` duration; log/receipt counts. The explicit-INCREMENT pilot also records a paired engine-INCREMENT minus direct-SQL-SUM sync delta, but because the direct path lacks equivalent guarantees, that delta is diagnostic only. LWW is a distinct-policy timing reference, not a same-semantics baseline. Units are milliseconds except counts.
- **Controlled:** same immutable generated operations and equivalent fresh bases per pair; fixed software and machine; alternating order.
- **Baseline:** current LWW sync measures a different resolution policy. Its timing may be reported as a distinct-strategy reference, not as same-semantics overhead. A direct application-level SUM scalar baseline now exists for exploratory use, but it lacks durable operation receipts, conflict persistence, quarantine, and checkpoint guarantees; it cannot support an end-to-end overhead claim.
- **Current evidence:** explicit-INCREMENT pilots have 13 paired trials at 1k/5%, and 10 paired trials each at 1k/20% and 1k/50%, with independent seeds, fresh state, alternating order, and compatible relevant source fingerprints. The 5k/20% and 10k/20% runs each have one trial and were collected only for runtime feasibility. No fair end-to-end baseline or confirmatory timing study exists. See `BASELINE_DESIGN.md` and `ABLATION_DESIGN.md`.
- **Acceptance evidence:** raw per-trial data, exact timing boundaries, failures retained, and descriptive distributions. No advantage claim from the historical two-trial artifacts or the non-equivalent direct-SQL pilot comparison.
- **Threats:** unmeasured CPU/storage/load; no memory instrumentation; filesystem cache and process effects; common-seed workloads.

### RQ3 — Which policy properties and integrity behaviors hold in enumerated engine histories?

- **Hypothesis:** Testable only as per-policy, per-schema, per-schedule statements. Do not hypothesize general convergence.
- **Independent variables:** policy, conflict shape, operation delivery order, duplicate/retry pattern, schema shape, and selected replica topology.
- **Dependent variables:** exact row values, status, operation IDs/receipts, quarantine contents, FK checks, ACK vectors, and retained log entries.
- **Baseline:** predeclared mathematical examples and independent state-machine/oracle code; never call the production resolver from the expected-value oracle.
- **Acceptance evidence:** property assertions only where algebraically valid; failure-injection tests assert complete state preservation or explicit recovery state.
- **Threats:** finite schedules and SQLite schemas; direct SQL/external writers; no formal proof.

### RQ4 — What recovery boundaries are tested for checkpoint-assisted pruning?

- **Hypothesis:** Existing tests cover selected manifest, snapshot, ACK, tail, and retry boundaries; they do not certify power-loss or multiprocess recovery.
- **Independent variables:** failure point, ACK state, membership, snapshot validity, replay-tail kind, and pruning progress.
- **Dependent variables:** hot logs, receipts, ACK state, checkpoint state, restored rows, and reported blocked/partial result.
- **Baseline:** exact state before injection, checked after failure and retry/restart.
- **Acceptance evidence:** each tested boundary preserves logs/data or performs idempotent roll-forward as specified. RESOLVE tails remain manual review.

## Trials and statistical plan

The existing nine-cell dataset has two timed pairs per cell but reuses seed 42 and one trace per cell. It is insufficient for inferential comparison. For future exploratory reproduction, target at least 10 independent paired workload seeds per configuration, each with fresh database state and one measurement per system; record seed and trace digest per trial. Alternate which system runs first using a balanced order schedule. Do not count multiple measurements on one trace as independent workload samples.

Before expanding to a confirmatory study, pilot representative cells at 1k, 5k, and 10k with multiple seeds. Estimate paired-difference variability, predeclare a smallest practically meaningful effect, and perform a paired sample-size/power calculation only if there is a comparable baseline and a defined inferential question. Specify alpha, target power, method, exclusions, and multiplicity handling before confirmatory runs. If these assumptions cannot be defended, report medians, IQR/range, and trial-level data descriptively; do not use significance language.

Record every attempted trial as success, failed, invalid, or interrupted with reason. Exclusions must be predeclared and all excluded records reported. No trial may be removed solely because its timing is inconvenient.

## Execution controls and metadata

For every new run record source revision and dirty-tree fingerprint; Python/package/SQLite versions; OS; machine and processor strings where obtainable; CPU core count where obtainable; available memory if measured; journal/synchronous/FK modes; schema; seeds; operation count/density; policy assignment; trace digest; pairing ID; order; and timing boundaries. Storage medium, thermal state, power plan, and host load must be measured or reported unavailable, never guessed.

Use new output directories. Preserve all raw trial records and logs. Keep historical and corrected-metric artifacts separate. Run the lightweight artifact validator before interpreting results.

For explicit-INCREMENT pilot files, validate an existing saved JSON/CSV pair and retained replica databases without rerunning the experiment:

```powershell
py -3.14 -m research.experiments.validate_increment_evaluation research/experiments/runs/increment-pilot-1000-5pct-20261020-final/increment_evaluation_1000_5pct.json
```

The validator independently recomputes the workload digest, additive expected values, SCR/RVAR, paired deltas, CSV agreement, and per-replica increment receipt uniqueness, and checks SQLite integrity. It validates the retained pilot artifacts; it does not establish that new measurements reproduce them.

The first exploratory pilot's `final1` JSON did not capture a Git revision or source-file hashes because the driver had not yet implemented source snapshotting. The current driver records both at run start. This instrumentation improvement does not retroactively enrich the earlier run; a later run is required for complete source-linked provenance.

## Execution status and matrix deferral

The existing SET-based 10k/20% repeated-artifact paired deltas vary from approximately +4.55 s to +53.39 s, and the two repeats use the same seed. The explicit-INCREMENT 10k/20% runtime pilot is a separate single-trial observation. The three 1,000-operation density cells have 13, 10, and 10 independent trials respectively; the six 5k/10k cells remain incomplete. The full independent-seed matrix is deferred pending review of this protocol and a defensible comparable baseline; no measurements are extrapolated from any artifact set.

A local assignment-based 1k/5% pilot with three independent seeds completed on 2026-10-20 as an exploratory diagnostic. Engine SUM conflict SCR was 100%, 98%, and 96%, exposing equal-SET intent ambiguity. Explicit-INCREMENT runs now provide 13 independent seeds at 1k/5%, and 10 each at 1k/20% and 1k/50%, plus one-trial runtime-feasibility records at 5k/20% and 10k/20%. The increment results cover all three densities at 1k only, not the nine-cell matrix; no result here is a confirmatory or fair end-to-end overhead comparison. See `research/experiments/BASELINE_DESIGN.md`, `research/experiments/PILOT_FINDINGS.md`, and the preserved raw run directories.

Two single-trial 20%-density scale runs were subsequently executed only to estimate runtime: 5,000 operations (seed 20261030, 90.113 s total trial duration) and 10,000 operations (seed 20261031, 226.433 s). They used fresh state and the same sequential-write/batch-sync protocol. Their per-system synchronization measurements are recorded in `research/experiments/PILOT_FINDINGS.md`; they are not additional paired samples for inference and are excluded from empirical manuscript results. The 10k run's engine-INCREMENT batch sync took 47.491 s, making a broad repeated matrix expensive. Do not extrapolate these two observations as a general scaling law.
