# SemanticSync — Research Metrics & Quantitative Framework

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Primary Research Metric: Semantic Correctness Rate ($SCR$)

The primary evaluative contribution of SemanticSync is the **Semantic Correctness Rate ($SCR$)**, defining the proportion of evaluated conflict outcomes that match a predetermined oracle. The stress harness has a narrower, explicit operational definition: it identifies conflict rows from the generated operation metadata and scores both replicas' final values for those rows only. Its denominator is twice the conflict-row count; a zero-conflict run has undefined SCR (N/A). Non-conflict rows are excluded. The expected additive values are generated before invoking either resolver.

$$SCR = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Result}_i = \text{GroundTruth}_i)}{N} \times 100\%$$

Where:
- For domain workloads, $N$ is the number of evaluated conflict attributes. For the stress harness, each replica's final value on a conflict row is one outcome, so $N$ is twice the number of conflict rows.
- $\mathbb{I}(\cdot) \in \{0, 1\}$ evaluates whether the output matches the independent ground-truth expectation.

### Target Performance
- **Baseline LWW:** Expected $SCR \le 35\%$ across heterogeneous workloads containing additive, append, or invariant columns.
- **SemanticSync:** Target $SCR \ge 90\%$, achieving $100\%$ on workloads where schema policies correctly model all divergent fields.

---

## 2. Secondary Metrics

### 2.1 State Convergence Rate ($CR$)
Measures whether replicas reach bitwise-identical relational states after synchronization completes. This is distinct from the stress harness's benchmark-row value agreement metric and is not measured by the 3×3 stress matrix:

$$CR = \frac{\sum_{k=1}^{R} \mathbb{I}(\text{Snapshot}_A^k \equiv \text{Snapshot}_B^k)}{R} \times 100\%$$

- **Target:** **$100.0\%$** for any benchmark that explicitly compares complete relational state. This target is not evidence that arbitrary schedules converge.

### 2.2 Benchmark-Row Value Agreement Rate (RVAR)
For the stress harness only, the percentage of row positions where the ordered `bench_rows.value` observations match across two replicas. RVAR excludes all other tables, schemas, logs, receipts, and quarantine state; it must not be described as full-database convergence.

### 2.3 Validation Rejection Accuracy ($VRA$)
For a workload with explicit domain range or relational constraints, quantifies the proportion of resolutions that preserve those constraints. This is not measured by the synthetic stress workload, which defines no such constraints; its VRA is N/A. Policy-assignment type rejection (for example, rejecting `SUM` on `TEXT`) is a separate validation test metric, not stress VRA.

$$VRA = \frac{TP + TN}{TP + TN + FP + FN} \times 100\%$$

- **Target:** **$100.0\%$**. Zero type-incompatible configurations (such as `AVG` on `TEXT` or `SUM` on `TEXT`) permitted to execute.

### 2.4 Computational Resolution Overhead ($\Delta t$)
The current domain endpoint measures conflict-evaluation-loop wall time divided by conflict count. The loop includes baseline scoring and semantic resolver calls, so it is not a pure resolver-only cost. The stress harness reports tracked-write latency percentiles and full batch sync times separately; its batch delta must not be labeled resolver overhead:

$$\Delta t = \frac{T_{\text{sync\_end}} - T_{\text{sync\_start}}}{N_{\text{conflicts}}} \quad (\mu s \text{ or } ms)$$

- **Target:** $\Delta t < 1.0\text{ ms}$ on commodity developer hardware.

### 2.5 Change Log Compaction Efficiency ($CE$) (Phase 6)
Measures storage savings achieved by pruning causally stable entries from `_ss_change_log`:

$$CE = \frac{\text{Bytes}_{\text{uncompacted}} - \text{Bytes}_{\text{compacted}}}{\text{Bytes}_{\text{uncompacted}}} \times 100\%$$
