# Existing Evidence Inventory

**Captured:** 2026-10-20. Saved artifacts were inspected and validated locally; no benchmark was run for this inventory.

## Code and tests

- Backend implementation is in `backend/engine/` and `backend/api/`; the synthetic harness is `backend/workloads/stress_harness.py`.
- The backend currently has 20 `test_*.py` modules. Relevant modules include `test_adversarial_resolution.py`, `test_bounded_operations.py`, `test_n_replica_sync.py`, `test_foreign_key_invariants.py`, `test_insert_collision_resolution.py`, `test_log_compaction.py`, `test_api.py`, and `test_stress_benchmark.py`.
- Earlier local full-suite evidence: 314 passed and one warning, 75.80 seconds. Latest local full-suite evidence after adding the research counterexample and source fingerprint capture: 319 passed and one warning, 92.61 seconds. Both runs used the dirty worktree and are not clean-checkout builds.
- Latest full-suite run after adding the increment artifact validator: 332 passed and one warning in 77.43 seconds using the local, non-sandbox Python 3.14 environment; the in-sandbox attempt stalled before the first Starlette TestClient request at Windows asyncio socket-pair setup. Focused compaction suite: 42 passed in 4.41 seconds. Neither result is a clean-checkout build or an expanded Phase 6 sign-off.

## Saved benchmark evidence

| Dataset | Files | Scope and evidence status |
|---|---:|---|
| `artifacts/benchmarks/repeated-stress-20261014/` | 9 JSON + 9 CSV | All nine size/density cells; two paired trials each; same seed 42 and same digest per cell; alternating baseline-first / SemanticSync-first order. Artifact validator passed consistency checks. These are descriptive repeated timings, not independent workload-seed trials. |
| `artifacts/benchmarks/historical-matrix-20261013/` | 9 JSON + 9 CSV | Historical single-run matrix. Keep distinct from later results. |
| `artifacts/benchmarks/historical-matrix-optimized-original-20261013/` | 9 JSON + 9 CSV | Original optimized-matrix records preserved from repository history; earlier SCR metric definition applies. |
| `artifacts/benchmarks/historical-matrix-optimized-metric-corrected-20261013/` | 9 JSON + 9 CSV | Later corrected-metric runs; not byte-identical to the original optimized records. These are a separate dataset, not a path-only rename. |
| `artifacts/test-evidence/phase3-full/` | Test-generated JSON, CSV, registry records | Execution evidence created by tests. Not benchmark results or a reproducible experimental dataset. |

The repeated-artifact validator reports the paired SemanticSync-minus-LWW batch-sync deltas per configuration, validates summary consistency, digests, trial metadata, and alternating order. It does not establish that the recorded run can be reproduced on another environment. Four repeated JSON artifacts omit redundant top-level `engine_settings`; trial-level policy, sync, FK, and journal metadata are present.

The two trials per cell share one deterministic operation trace. Trial order alternates, but the seed does not vary across trials. The large observed paired-delta ranges at 5k/20% and 10k/20% remain in the data; no trial was discarded. Their cause is unresolved.

An additional three-seed exploratory engine pilot is stored at `research/experiments/runs/pilot-1000-5pct-20261020-final1/`. It is not part of the nine-cell saved stress matrix. It found engine SUM SCR values of 100%, 98%, and 96% because equal replica assignments are omitted from state-diff conflicts while the additive oracle counts both as contributions. Treat it as a counterexample/diagnostic, not as confirmatory evidence or fair performance comparison.

The distinct `INCREMENT` operation model has a separate three-seed exploratory run at `research/experiments/runs/increment-pilot-1000-5pct-20261020-final/`. It covers only 1,000 operations at 5% conflict density. An independent check verified all trace digests, expected conflict values, engine and application SUM SCR, LWW SCR under the additive oracle, runner hash, CSV rows, per-replica increment receipts, and paired sync-delta summary. The observed timing comparison is descriptive only because the direct-SQL baseline lacks equivalent operation-history and recovery guarantees. This pilot is not combined with the historical SET-based matrix.

## Supplied review-paper collection

The user-provided collection at `C:\Users\ASMIT\Downloads\DBMS-REVIEWPAPERS` contained **25 PDF files** at inventory time. A bundled local PDF reader extracted first-page title/author text for the files. This establishes that the local files are readable and useful for related-work review; it does not by itself validate venue, DOI, version, or publication status. The collection includes materials on CRDTs, replicated SQL/relations, local-first integrity, operation/state CRDT verification, and SemanticSync-adjacent systems including Synql, Riffle, CRDV, Antidote SQL, LoRe, and Merge What You Can, Fork What You Can't. The folder is external to the repository and may later receive additional papers; inventory must be repeated before a final citation audit.

## Existing documentation and paper outputs

- Research protocol/materials: `research/RESULTS_PROTOCOL.md`, `research/EXPERIMENTAL_DESIGN.md`, `research/METRICS.md`, `research/LITERATURE_REVIEW.md`, and `research/PAPER_PLAN.md`.
- Manuscript representations: Markdown, HTML, and LLNCS LaTeX source/bibliography under `docs/`.
- `docs/KNOWN_LIMITATIONS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/ROADMAP.md`, and `docs/TRACEABILITY_MATRIX.md` document selected behavior and limits. They are useful leads but are not proof without source/test review.
- The domain benchmark endpoint currently returns `illustrative_unvalidated`; comparative metrics are null. Historical proxy-based domain metrics are not evidence.

## Important evidence gaps

1. Two repeated trials do not provide independent workload-seed variation or support inferential claims.
2. LWW and SUM have different semantics under the additive SCR oracle; this is not a neutral comparative correctness baseline.
3. No saved repeated workload measures VRA, whole-database convergence, concurrent writers, CPU, memory, or storage throughput.
4. Existing timing artifacts omit host load and storage details; old runs cannot be retroactively enriched with those measurements.
5. Selected tests establish only their exercised policies, schemas, histories, and schedules. They do not prove arbitrary-schedule convergence or formal correctness.
6. Checkpoint docs explicitly retain process-local coordination, manual review of RESOLVE tails, and uncertified power-loss durability.
7. The supplied papers need bibliographic and claim-level mapping; PDF filenames and first-page extraction alone are not a complete related-work review.
