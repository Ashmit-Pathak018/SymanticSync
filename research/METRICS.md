# SemanticSync — Research Metrics & Quantitative Framework

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Primary Research Metric: Semantic Correctness Rate ($SCR$)

The primary evaluative contribution of SemanticSync is the **Semantic Correctness Rate ($SCR$)**, defining the proportion of concurrent conflicts resolved in conformance with predetermined domain invariants:

$$SCR = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Result}_i = \text{GroundTruth}_i)}{N} \times 100\%$$

Where:
- $N$ is the total count of evaluated concurrent conflicts.
- $\mathbb{I}(\cdot) \in \{0, 1\}$ evaluates whether the output matches the independent ground-truth expectation.

### Target Performance
- **Baseline LWW:** Expected $SCR \le 35\%$ across heterogeneous workloads containing additive, append, or invariant columns.
- **SemanticSync:** Target $SCR \ge 90\%$, achieving $100\%$ on workloads where schema policies correctly model all divergent fields.

---

## 2. Secondary Metrics

### 2.1 State Convergence Rate ($CR$)
Measures whether replicas reach bitwise-identical relational states after synchronization completes:

$$CR = \frac{\sum_{k=1}^{R} \mathbb{I}(\text{Snapshot}_A^k \equiv \text{Snapshot}_B^k)}{R} \times 100\%$$

- **Target:** **$100.0\%$** across all test runs for both Baseline and SemanticSync. Any divergence represents a synchronization failure.

### 2.2 Validation Rejection Accuracy ($VRA$)
Quantifies the system's ability to identify and reject invalid schema-policy pairings before runtime execution:

$$VRA = \frac{TP + TN}{TP + TN + FP + FN} \times 100\%$$

- **Target:** **$100.0\%$**. Zero type-incompatible configurations (such as `AVG` on `TEXT` or `SUM` on `TEXT`) permitted to execute.

### 2.3 Computational Resolution Overhead ($\Delta t$)
Measures the per-conflict algorithmic processing latency:

$$\Delta t = \frac{T_{\text{sync\_end}} - T_{\text{sync\_start}}}{N_{\text{conflicts}}} \quad (\mu s \text{ or } ms)$$

- **Target:** $\Delta t < 1.0\text{ ms}$ on commodity developer hardware.

### 2.4 Change Log Compaction Efficiency ($CE$) (Phase 6)
Measures storage savings achieved by pruning causally stable entries from `_ss_change_log`:

$$CE = \frac{\text{Bytes}_{\text{uncompacted}} - \text{Bytes}_{\text{compacted}}}{\text{Bytes}_{\text{uncompacted}}} \times 100\%$$
