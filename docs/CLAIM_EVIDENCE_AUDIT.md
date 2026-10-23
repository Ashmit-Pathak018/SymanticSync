# SemanticSync — Comprehensive Claim-to-Evidence Audit

**Project:** SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases  
**Authors:** Pathak Ashmit Akhilesh and Yash Bohra  
**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  
**Evaluation Target:** Camera-ready IEEE manuscript (`docs/manuscript_latex/IEEE_DEMO_PAPER.tex`), experimental run data (`research/experiments/runs/increment-full-matrix-20261020-144638`), and codebase (`backend/`).

---

## 1. Executive Audit Summary

This audit cross-references every scientific, empirical, and architectural claim made in the SemanticSync research paper against the actual implementation files, automated pytest test suites, and empirical benchmark artifacts.

- **Total Scientific Claims Audited:** 24
- **Verification Status:**
  - **Verified (Direct Code & Empirical Proof):** 20 claims
  - **Partially Supported (Bounded by Stated Assumptions):** 4 claims (clearly qualified in manuscript)
  - **Unsupported / Fabricated:** 0 claims
- **Empirical Reproducibility:** All 90 matrix trials independently pass `research.experiments.validate_increment_evaluation` with zero integrity violations and exact oracle match.

---

## 2. Claim-to-Evidence Matrix

| ID | Manuscript Claim | Source Implementation | Test / Experiment Evidence | Evidence Status | Recommended Formulation / Qualification |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **C1** | Implements 8 schema-assigned merge policies (`SUM`, `BOUNDED_SUM`, `AVG`, `APPEND`, `LWW`, `MIN`, `MAX`, `REJECT`) bound to SQLite columns. | [`backend/engine/policy_registry.py`](../backend/engine/policy_registry.py), [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py) | `backend/tests/test_resolution.py`, `backend/tests/test_audit_correctness.py` (all pass) | **Verified** | Accurately describes schema-level pairwise resolution rules. |
| **C2** | `SUM` policy computes additive delta: $v_{\text{base}} + (v_A - v_{\text{base}}) + (v_B - v_{\text{base}})$. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L90-L115) | `test_audit_correctness.py::test_symmetric_policies_commutativity` | **Verified** | Fixed-base additive delta merge; non-idempotent; requires operation identity for replay safety. |
| **C3** | `BOUNDED_SUM` enforces range invariants $[\min, \max]$ without clamping, emitting $ot$ on overflow. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L117-L140) | `backend/tests/test_bounded_operations.py` (all pass) | **Verified** | Invariant check is fail-fast and deterministic; preserves domain integrity. |
| **C4** | `AVG` is commutative but strictly non-associative: $(v_A + v_B)/2.0$. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L142-L160) | `test_audit_correctness.py::test_avg_non_associativity_proof` | **Verified** | Explicitly documented as suitable only for pairwise sensor merges, not arbitrary $N$-way trees. |
| **C5** | `APPEND` provides pairwise commutative string merging by sorting deltas by replica ID. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L162-L185) | `test_audit_correctness.py::test_append_commutativity_via_replica_id_sorting` | **Verified** | Pairwise deterministic; does not construct an element-level replicated text sequence (not a sequence CRDT). |
| **C6** | `LWW` breaks timestamp ties deterministically using lexicographic `replica_id`. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L187-L210) | `test_audit_correctness.py::test_lww_strict_commutativity_with_identical_timestamps_tie_breaking` | **Verified** | Syntactically deterministic; disregards business semantics. |
| **C7** | `MIN` and `MAX` policies form complete semilattices (commutative, associative, idempotent). | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L212-L235) | `test_audit_correctness.py::test_min_max_associativity` | **Verified** | Standard convergent lattice properties verified across numeric domains. |
| **C8** | `REJECT` emits $ot$ (flagged for review) to prevent automated silent overwrites. | [`backend/engine/semantic_resolver.py`](../backend/engine/semantic_resolver.py#L237-L255) | `test_audit_correctness.py::test_reject_always_returns_flagged` | **Verified** | Halts automated merge; stores conflict in `MergeManager` awaiting manual operator action. |
| **C9** | Explicit `apply_increment` assigns unique `origin_id`, logs signed deltas, and prevents duplicate delivery replay. | [`backend/engine/crdt_sync.py`](../backend/engine/crdt_sync.py#L240-L320) | `backend/tests/test_sync.py::test_increment_operations_preserve_two_independent_contributions_and_replay_once` | **Verified** | Distinct from absolute `SET`; logs receipts in `_ss_change_log` and `_ss_compacted_receipts`. |
| **C10** | Hybrid Logical Clock (HLC) updates physical time and logical counter across local writes and message receives. | [`backend/engine/crdt_sync.py`](../backend/engine/crdt_sync.py#L71-L109) | `backend/tests/test_audit_correctness.py::test_hlc_monotonicity_and_ordering` | **Verified** | Follows Kulkarni et al. (2014); formula correctly incorporates $pt_{\text{wall}}$ with 4-case logical advance. |
| **C11** | HLC provides total deterministic tie-breaking but does not replace vector clocks in multi-replica meshes. | [`backend/engine/crdt_sync.py`](../backend/engine/crdt_sync.py#L115-L130) | `test_sync.py`, manuscript Section II-B | **Verified** | Accurately scoped in Section II-B; does not claim arbitrary mesh causality. |
| **C12** | Foreign-key quarantine enforces `PRAGMA foreign_keys = ON`, moving child rows to `_ss_quarantine` before parent deletion. | [`backend/engine/fk_quarantine.py`](../backend/engine/fk_quarantine.py#L40-L150) | `backend/tests/test_foreign_key_invariants.py` (all pass) | **Verified** | Atomically introspects foreign keys, isolates orphans, deletes parent, and verifies `foreign_key_check`. |
| **C13** | Quarantined children can be inspected and restored to a resurrected or reassigned parent. | [`backend/engine/fk_quarantine.py`](../backend/engine/fk_quarantine.py#L160-L240), [`backend/api/routes_conflicts.py`](../backend/api/routes_conflicts.py) | `test_foreign_key_invariants.py::test_restore_quarantined_child` | **Verified** | Full lifecycle: `QUARANTINED` -> validation -> atomic reinsertion -> `RESTORED`. |
| **C14** | Checkpoint log compaction requires unanimous acknowledgment vectors, payload hash match, and stable HLC horizon. | [`backend/engine/log_compaction.py`](../backend/engine/log_compaction.py#L50-L180) | `backend/tests/test_log_compaction.py` (all pass) | **Verified** | Prunes hot log only below $H_{\text{stable}}$; writes receipts to `_ss_compacted_receipts`. |
| **C15** | Pruned operations re-delivered by slow replicas are suppressed via `_ss_compacted_receipts`. | [`backend/engine/log_compaction.py`](../backend/engine/log_compaction.py#L185-L230) | `test_log_compaction.py::test_redelivery_after_compaction_suppressed` | **Verified** | Cryptographic payload hash lookup suppresses duplicate execution safely. |
| **C16** | 90-trial evaluation matrix covers 1k/5k/10k operations at 5%/20%/50% conflict density (10 seeds per cell). | `research/experiments/runs/increment-full-matrix-20261020-144638` | `research/experiments/validate_increment_evaluation.py` (all 90 pass) | **Verified** | Exact seed ranges: 20263000 to 20263809. 10 independent trials per configuration. |
| **C17** | Semantic Correctness Rate (SCR) reaches 100.0% for SemanticSync against arithmetic additive oracle. | `AGGREGATE_RESULTS.csv`, `research/experiments/runs/` | Tested in `test_increment_evaluation.py`, validated by validator script | **Verified** | All conflict rows match $v_{\text{base}} + \Delta_A + \Delta_B$ across both replicas ($2 \times C$ checks). |
| **C18** | Generic LWW scores 0.0% SCR on conflict rows under the additive oracle. | `AGGREGATE_RESULTS.csv`, `test_increment_evaluation.py` | Validated in all 90 trial runs | **Verified** | LWW selects one timestamp and overwrites the other, permanently erasing one delta contribution. |
| **C19** | Row Value Agreement (RVAR) reaches 100.0% across all 90 matrix trials. | `AGGREGATE_RESULTS.csv`, trial JSON artifacts | Evaluated via direct SQLite table comparison across replicas | **Verified** | Evaluates ordered `bench_rows.value` vector; proves pairwise value convergence. |
| **C20** | Batch sync timing deltas scale from 449.7 ms (1k/5%) to 84,368.7 ms (10k/50%). | `AGGREGATE_RESULTS.csv`, manuscript Table IV | Derived from recorded trial timestamps | **Verified** | Median $\Delta = T_{\text{inc}} - T_{\text{app}}$ calculated accurately with corresponding IQRs. |
| **C21** | Timing differences reflect mechanism costs (logging, receipts, checks) rather than general performance advantage. | Manuscript Section VI-C, discussion | `IEEE_DEMO_PAPER.tex#L320`, `FINAL_DEMO_PAPER.md#L260` | **Verified** | Paper explicitly disclaims performance superiority; clarifies narrower baseline comparison. |
| **C22** | Historical SET-based diffing scored 97.5%–98.25% SCR due to equal-valued independent updates ($v_A = v_B$). | `artifacts/benchmarks/historical-matrix-20261013/` | Manuscript Table II & Table III | **Partially Supported (Historical)** | Identified state-diffing limitation; clearly separated from operation-based INCREMENT matrix. |
| **C23** | System handles single-column primary and foreign keys; composite keys and circular dependencies fail-stop. | [`backend/engine/schema_inspector.py`](../backend/engine/schema_inspector.py), [`backend/engine/fk_quarantine.py`](../backend/engine/fk_quarantine.py) | `test_foreign_key_invariants.py::test_composite_key_fail_stop` | **Partially Supported (Scoped)** | Clearly noted as an explicit design boundary in Section VII of the paper. |
| **C24** | Pairwise policies operate within two-replica sync boundaries and do not constitute an arbitrary multi-replica mesh proof. | [`backend/engine/crdt_sync.py`](../backend/engine/crdt_sync.py), manuscript Section II-A & VII | Manuscript Section II-A, Section VII | **Partially Supported (Scoped)** | Paper explicitly documents pairwise scope and warns against claiming generalized CRDT convergence. |

---

## 3. Discrepancy & Resolution Log

1. **Host Environment Attribution:**
   - *Initial Text:* Claimed execution on an "isolated host".
   - *Audit Finding:* Notes confirm a standard Windows 11 host (Python 3.14.3, SQLite 3.50.4), but no isolated CPU affinity / bare-metal server enclosure was established.
   - *Resolution Applied:* Revised manuscript and documentation to state: `"a single Windows 11 host (Python 3.14.3, SQLite 3.50.4, journal_mode = DELETE)"`.
2. **Hybrid Logical Clock Piecewise Equation:**
   - *Initial Text:* Mathematical formula omitted local wall-clock time $pt_{\text{wall}}$ and reset logical counter $l$ to 0 inappropriately.
   - *Audit Finding:* Code inspection of `backend/engine/crdt_sync.py::tick()` revealed standard Kulkarni et al. (2014) logic incorporating $pt_{\text{wall}}$.
   - *Resolution Applied:* Derived exact 4-case equation directly from code and reconciled in both LaTeX and Markdown sources.
3. **Table I Column Wrapping & LaTeX Layout:**
   - *Initial Text:* Table I had overfull hbox warnings and awkward column breaks on `INTEGER, REAL, NUMERIC`.
   - *Audit Finding:* Column specifications in LaTeX exceeded column margins.
   - *Resolution Applied:* Formatted concisely (`Numeric (INT, REAL)`, `Text (TEXT)`), adjusted widths to `0.15	extwidth, 0.18	extwidth, 0.27	extwidth, 0.32	extwidth`, eliminating all overfull warnings.

---

## 4. Final Verdict

The implementation and experimental data **fully support** the claims presented in the camera-ready manuscript [`docs/manuscript_latex/IEEE_DEMO_PAPER.pdf`](../docs/manuscript_latex/IEEE_DEMO_PAPER.pdf). All identified boundaries, historical limitations, and mechanism costs are transparently qualified.
