# SemanticSync — Requirements-to-Test Traceability Matrix

**Version:** 2.1 (Phase 1 Follow-Up)  
**Status:** Verification Baseline — 82 tests passing

---

This matrix links all major functional requirements and scientific guarantees to specific automated tests in the repository.

| Requirement ID | Guarantee / Specification | Target Module | Verified Test Case(s) | Status |
|---|---|---|---|---|
| **REQ-SCH-01** | SQLite schema introspection via PRAGMA | `engine/schema_inspector.py` | `test_schema.py::test_inspect_known_schema_columns`, `test_inspect_returns_full_dict` | ✅ Verified Passing |
| **REQ-SCH-02** | Primary Key column detection | `engine/schema_inspector.py` | `test_schema.py::test_inspect_primary_key_detected` | ✅ Verified Passing |
| **REQ-SCH-03** | SQLite affinity type normalization (5 types)| `engine/schema_inspector.py` | `test_schema.py::test_normalize_type_coverage` (24 parametrized test cases) | ✅ Verified Passing |
| **REQ-VAL-01** | Valid policy-datatype assignment acceptance| `engine/policy_validator.py` | `test_validation.py::test_valid_combinations`, `test_batch_validation` | ✅ Verified Passing |
| **REQ-VAL-02** | Invalid assignment rejection (`422`) | `engine/policy_validator.py` | `test_validation.py::test_invalid_type_combinations` | ✅ Verified Passing |
| **REQ-VAL-03** | Unknown policy name rejection | `engine/policy_validator.py` | `test_validation.py::test_unknown_policy` | ✅ Verified Passing |
| **REQ-RES-01** | `SUM` additive delta reconciliation | `engine/semantic_resolver.py` | `test_resolution.py::test_sum_additive_delta` | ✅ Verified Passing |
| **REQ-RES-02** | `SUM` commutativity: $f(A, B) = f(B, A)$ | `engine/semantic_resolver.py` | `test_resolution.py::test_sum_commutativity` | ✅ Verified Passing |
| **REQ-RES-03** | `AVG` arithmetic mean calculation | `engine/semantic_resolver.py` | `test_resolution.py::test_avg_mean` | ✅ Verified Passing |
| **REQ-RES-04** | `AVG` commutativity: $f(A, B) = f(B, A)$ | `engine/semantic_resolver.py` | `test_resolution.py::test_avg_commutativity` | ✅ Verified Passing |
| **REQ-RES-05** | `APPEND` text preservation & sorting | `engine/semantic_resolver.py` | `test_resolution.py::test_append_text`, `test_append_one_sided_change` | ✅ Verified Passing |
| **REQ-RES-06** | `LWW` HLC timestamp order & tie-break | `engine/semantic_resolver.py` | `test_resolution.py::test_lww_timestamps`, `test_lww_tie_break` | ✅ Verified Passing |
| **REQ-RES-07** | `MIN` and `MAX` numeric extrema | `engine/semantic_resolver.py` | `test_resolution.py::test_min_and_max` | ✅ Verified Passing |
| **REQ-RES-08** | `REJECT` safety stop (unmerged flag) | `engine/semantic_resolver.py` | `test_resolution.py::test_reject_policy` | ✅ Verified Passing |
| **REQ-SYN-01** | 2-replica fork, mutate, converge lifecycle| `engine/crdt_sync.py` | `test_sync.py::test_replica_creation_and_sync` | ✅ Verified Passing |
| **REQ-BEN-01** | Workload setup & ground-truth validation | `workloads/` | `test_benchmark.py::test_inventory_workload_setup`, `test_notes_workload_setup`, `test_health_workload_setup` | ✅ Verified Passing |
| **REQ-API-01** | Health, Seed, Databases API contracts | `api/` | `test_api.py::test_health_and_root`, `test_seed_and_list_databases` | ✅ Verified Passing |
| **REQ-API-02** | Policy validation endpoint | `api/routes_policies.py` | `test_api.py::test_validate_policy_endpoint` | ✅ Verified Passing |
| **REQ-API-03** | Parameterized SQL query console | `api/routes_query.py` | `test_api.py::test_query_endpoint` | ✅ Verified Passing |
| **REQ-API-04** | Benchmark execution & metrics retrieval | `api/routes_benchmark.py` | `test_api.py::test_benchmark_endpoint` | ✅ Verified Passing |
| **REQ-AUD-01** | Algebraic commutativity & semilattice bounds| `engine/semantic_resolver.py` | `test_audit_correctness.py::TestPolicyAlgebraicProperties` (8 parametrized tests) | ✅ Verified Passing |
| **REQ-AUD-02** | Formal proof of AVG non-associativity | `engine/semantic_resolver.py` | `test_audit_correctness.py::test_avg_non_associativity_proof` | ✅ Verified Passing |
| **REQ-AUD-03** | Formal proof of SUM non-idempotency | `engine/semantic_resolver.py` | `test_audit_correctness.py::test_sum_non_idempotency_hazard` | ✅ Verified Passing |
| **REQ-AUD-04** | HLC monotonicity and causal ordering | `engine/crdt_sync.py` | `test_audit_correctness.py::test_hlc_monotonicity_and_ordering` | ✅ Verified Passing |
| **REQ-AUD-05** | Repeated sync idempotency (zero duplicates) | `engine/crdt_sync.py` | `test_audit_correctness.py::test_repeated_sync_idempotency_on_converged_replicas` | ✅ Verified Passing |
| **REQ-AUD-06** | Single-sided updates treated as clean updates| `engine/conflict_detector.py` | `test_audit_correctness.py::test_single_sided_update_does_not_trigger_conflict` | ✅ Verified Passing |
| **REQ-AUD-07** | 3-replica pairwise sync convergence (LWW) | `engine/crdt_sync.py` | `test_audit_correctness.py::test_three_replica_pairwise_sync_convergence_with_lww` | ✅ Verified Passing |
| **REQ-AUD-08** | AVG algebraic idempotency: avg(x,x)=x; sync-level non-idempotency under stale base | `engine/semantic_resolver.py` | `test_audit_correctness.py::test_avg_algebraic_idempotency` | ✅ Verified Passing |
| **REQ-AUD-09** | APPEND multi-operation per replica, duplicate delivery idempotency | `engine/crdt_sync.py` | `test_audit_correctness.py::test_append_multi_operation_and_reordering` | ✅ Verified Passing |
| **REQ-AUD-10** | Write-back HLC strictly dominates both predecessor timestamps | `engine/crdt_sync.py`, `engine/conflict_detector.py` | `test_audit_correctness.py::test_hlc_write_back_causal_dominance` | ✅ Verified Passing |
| **REQ-EXT-01** | INSERT vs. INSERT collision detection | `engine/conflict_detector.py` | `Phase 2 planned` (`test_mutation_conflicts.py`) | 📋 Planned |
| **REQ-EXT-02** | UPDATE vs. DELETE tombstone resolution | `engine/conflict_detector.py` | `Phase 2 planned` (`test_mutation_conflicts.py`) | 📋 Planned |
| **REQ-EXT-03** | `BOUNDED_SUM` underflow invariant flag | `engine/semantic_resolver.py` | `Phase 3 planned` (`test_bounded_operations.py`)| 📋 Planned |
| **REQ-EXT-04** | Multi-replica ($N \ge 3$) sync convergence | `engine/crdt_sync.py` | `Phase 3 planned` (`test_n_replica_sync.py`) | 📋 Planned |
| **REQ-EXT-05** | Scaled stress benchmark ($N=1000$) | `workloads/` | `Phase 4 planned` (`test_stress_benchmark.py`) | 📋 Planned |
| **REQ-EXT-06** | Foreign-key orphan quarantine | `engine/crdt_sync.py` | `Phase 5 planned` (`test_foreign_key_invariants.py`)| 📋 Planned |
| **REQ-EXT-07** | Causal stability change-log pruning | `engine/crdt_sync.py` | `Phase 6 planned` (`test_log_compaction.py`) | 📋 Planned |
