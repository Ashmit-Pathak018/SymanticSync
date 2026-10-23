# Test Coverage Matrix

Earlier backend verification on this dirty worktree completed with 314, 319, and 331 passing tests. Later runs completed with **332 passed, 1 warning in 77.43 seconds**, **332 passed, 1 warning in 78.23 seconds**, **334 passed in 81.22 seconds**, and **335 passed, 1 warning in 83.94 seconds**. After adding single-run summary coverage, the latest local run completed with **336 passed, 1 warning in 85.15 seconds**. The mapping below summarizes finite regression coverage, not exhaustive proof.

| Area / claim | Tests | Assertions evidenced | Not established |
|---|---|---|---|
| Resolver policy algebra | `test_adversarial_resolution.py::test_generated_policy_commutativity_for_valid_domains`, `test_generated_valid_associativity_and_idempotence_boundaries`, `test_avg_non_associativity_is_explicit`, `test_append_empty_unicode_none_and_identical_inputs` | Generated values and explicit AVG/APPEND edge examples. | Infinite-domain proof; APPEND N-way properties. |
| BOUNDED_SUM bounds and receipts | `test_bounded_operations.py` boundary, trigger, precision, pending/retry, relay, and 3-way tests | Inclusive bounds, no clamping, stable IDs, exact values, selected receipt idempotency and recovery. | Arbitrary permutations/histories; semantic safety for direct SQL. |
| N-replica schedules | `test_n_replica_sync.py::test_mesh_topologies_reversed_order_duplicates_and_restart` | N=3/5 selected star, ring, complete-pair schedules; reversed edge order, duplicate replay, restart; exact values and receipts. | All schedules, concurrency, arbitrary topology, general convergence. |
| Ordinary operation replay | `test_sync.py`, `test_phase_2_2_integrity.py`, `test_resolution.py`, `test_insert_collision_resolution.py` | Selected update/delete/insert, replay, conflict, resolution and failure semantics. | General histories, all SQLite affinity/trigger behaviors, external writers. |
| INSERT collision manual resolution | `test_insert_collision_resolution.py` tests for PK/UNIQUE collision, custom replacement, uniqueness failure, second-replica failure, retry, stale rows, referenced rows | Preservation of payload snapshots, audit/retry behavior and selected two-replica failure rollback. | General relational rewrites, composite parent identity, automatically safe re-keying. |
| Foreign-key quarantine | `test_foreign_key_invariants.py` paths for local/received/API/paired deletes, nested rows, alternate unique parent columns, composite child/FK, parent-key update, rollback, relink | Selected supported shapes and enumerated tracked paths; unsupported schemas reject. | Every SQLite action/trigger/schema; SQL console remains untracked and does not quarantine cascade children. |
| Checkpoint creation/recovery | `test_log_compaction.py` ACK, store, snapshot, tail, partial prune, registry failure, isolation, and lock tests | Exact membership/evidence validation and selected restart/retry failure boundaries. | Power-loss durability, cross-process coordination, auto RESOLVE-tail replay, arbitrary offline histories. |
| Stress metrics/artifacts | `test_stress_benchmark.py` SCR/RVAR/oracle/metadata/aggregation/artifact/API tests | Conflict-only SCR, null zero-conflict SCR, narrow RVAR, real workload execution, saved schema. | Full DB convergence, independent-seed statistical analysis, concurrent writers, fair same-semantics performance baseline. |
| Domain benchmark API | `test_domain_benchmark_status.py` | Current status is illustrative/unvalidated and comparative metrics unavailable. | Domain scenario correctness or performance. |

## Test execution record

The added characterization test `backend/tests/test_research_evaluation.py::test_equal_concurrent_assignments_are_a_counterexample_for_additive_intent` exercises the actual two-replica engine path. It demonstrates that two `100 -> 110` assignments produce no detected conflict and remain 110, while the declared independent-contribution oracle calculates 120. This is a documented counterexample, not a passing correctness property.

Command executed in this local session on 2026-10-20:

```powershell
py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-research-fb45a2a96f434ead9e22f955e4f89a7f -o faulthandler_timeout=15
```

Earlier observed results were **314 passed in 75.80s**, **319 passed in 94.77s**, **319 passed in 92.61s**, **331 passed in 77.49s**, **332 passed, 1 warning in 77.43s**, **332 passed, 1 warning in 78.23s**, **334 passed, 1 warning in 81.22s**, and **335 passed, 1 warning in 83.94s**. Latest observed result: **336 passed, 1 warning in 85.15s** using `py -3.14 -m pytest backend/tests/ -q --tb=short --basetemp .pytest-active-full-final-20261020 -o faulthandler_timeout=30`. This completed locally in the dirty Windows worktree. The warning concerned Starlette's deprecated HTTPX/TestClient integration. No test was skipped. This result is tied to the current worktree and environment.
