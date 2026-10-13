# SemanticSync — Baseline Definition & Comparative Model

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Baseline Specification: Generic Last-Write-Wins (LWW)

In distributed database benchmarking, the proposed system must be compared against a recognized standard. The primary baseline for SemanticSync is the **Generic Last-Write-Wins (LWW) Register CRDT**, which represents the default conflict resolution mechanism in systems such as Cassandra, CR-SQLite column registers, and CouchDB winning revisions.

### Formal Operation of LWW Baseline
Every replica mutation writes an attribute value associated with an HLC timestamp $\tau = \langle pt, l, \text{node\_id} \rangle$.

Given concurrent divergent mutations $M_A = \langle V_A, \tau_A \rangle$ and $M_B = \langle V_B, \tau_B \rangle$:
$$\text{Resolve}_{\text{LWW}}(M_A, M_B) = \begin{cases}
V_B & \text{if } \tau_B > \tau_A \\
V_A & \text{if } \tau_A > \tau_B \\
\text{lexicographic\_winner}(V_A, V_B) & \text{if } \tau_A = \tau_B
\end{cases}$$

---

## 2. Baseline Fairness Guarantee

To avoid strawman comparison:
1. **Identical Inputs:** The baseline receives the exact same inputs ($V_A, V_B, \tau_A, \tau_B$) as the SemanticSync resolver.
2. **Identical Timestamps:** Timestamps assigned to replica mutations follow the exact same distribution.
3. **No Artificial Delays:** Baseline resolution execution is measured directly without synthetic throttling.

---

## 3. Structural Failure Modes of Generic LWW

The benchmark quantitatively demonstrates the specific failure modes of LWW when applied to relational attributes:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LWW FAILURE TAXONOMY                            │
├─────────────────────┬──────────────────────────┬───────────────────────┤
│ Column Semantics    │ Generic LWW Outcome      │ Formal Failure Mode   │
├─────────────────────┼──────────────────────────┼───────────────────────┤
│ Additive Counter    │ Retains only later value │ Lost Update / Delta   │
│ Text Annotation     │ Retains only later text  │ Silent Truncation     │
│ Sensor Observation  │ Discards one reading     │ Sample Loss           │
│ Immutable Invariant │ Silently overwrites key  │ Invariant Violation   │
└─────────────────────┴──────────────────────────┴───────────────────────┘
```

These structural failure modes are the root cause of the low Semantic Correctness Rate ($SCR \le 35\%$) observed on generic baselines.
