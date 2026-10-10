# SemanticSync — Evaluation Metrics

**Version:** 1.0

---

## 1. Primary Metric: Semantic Correctness Rate (SCR)

The primary benchmark metric introduced by this research is the **Semantic Correctness Rate ($SCR$)**, defined as the proportion of concurrent conflicts resolved in alignment with domain ground truth:

$$SCR = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Result}_i = \text{GroundTruth}_i)}{N} \times 100\%$$

Where:
- $N$ is the total number of evaluated concurrent conflict scenarios.
- $\mathbb{I}(\cdot)$ is the indicator function returning $1$ if the evaluated resolution equals ground truth, and $0$ otherwise.

### Acceptance Threshold
- **Baseline LWW:** Expected $SCR \le 35\%$ across heterogeneous workloads.
- **SemanticSync:** Expected $SCR \ge 90\%$ (targeting $100\%$ on cleanly defined schema domains).

---

## 2. Secondary Metric: Convergence Rate (CR)

Measures whether replicas achieve bitwise state equivalence following synchronization:

$$CR = \frac{\sum_{k=1}^{R} \mathbb{I}(\text{ReplicaState}_A^k \equiv \text{ReplicaState}_B^k)}{R} \times 100\%$$

Where $R$ is the number of synchronized replica pairs.
- Target for **both** Baseline LWW and SemanticSync: **$100.0\%$**.

---

## 3. Secondary Metric: Validation Rejection Accuracy (VRA)

Quantifies the system's ability to reject syntactically incompatible policy assignments at schema configuration time:

$$VRA = \frac{TP + TN}{TP + TN + FP + FN} \times 100\%$$

- Evaluated across test matrices in `backend/tests/test_validation.py`.
- Target: **$100.0\%$** (zero type-mismatched policies permitted into runtime).

---

## 4. Performance Metric: Resolution Overhead ($\Delta t$)

The computational latency incurred by three-way diff inspection and policy resolution:

$$\Delta t = \frac{T_{\text{sync\_end}} - T_{\text{sync\_start}}}{N_{\text{conflicts}}} \quad (\text{measured in milliseconds or microseconds})$$

- Target: $\Delta t < 1.0\text{ ms}$ per cell conflict on commodity hardware.
