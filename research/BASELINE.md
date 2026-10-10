# SemanticSync — Baseline Definition

**Version:** 1.0

---

## 1. Definition of Generic Last-Write-Wins (LWW)

The industry-standard baseline against which SemanticSync is benchmarked is the **Generic Last-Write-Wins (LWW) Register CRDT**.

In a standard LWW-Register implementation:
- Every cell mutation carries a timestamp $\tau = \langle pt, l, node\_id \rangle$.
- Given two concurrent modifications $M_A = \langle V_A, \tau_A \rangle$ and $M_B = \langle V_B, \tau_B \rangle$ where $\tau_A \neq \tau_B$:

$$\text{Resolve}_{\text{LWW}}(M_A, M_B) = \begin{cases} 
V_B & \text{if } \tau_B > \tau_A \\
V_A & \text{if } \tau_A > \tau_B \\
\text{tie\_break}(V_A, V_B) & \text{if } \tau_A = \tau_B
\end{cases}$$

---

## 2. Baseline Simulation in the Benchmark Suite

To ensure fair comparison, the benchmark harness (`backend/api/routes_benchmark.py` and `backend/tests/test_benchmark.py`) models the baseline using the exact same conflict candidates:

```python
# Baseline LWW simulation
def evaluate_baseline(conflict_scenario, ts_a, ts_b):
    if ts_b >= ts_a:
        winning_value = conflict_scenario["value_b"]
    else:
        winning_value = conflict_scenario["value_a"]
        
    is_correct = (winning_value == conflict_scenario["expected_baseline_result"])
    return winning_value, is_correct
```

---

## 3. Inherent Failure Modes of Generic LWW

| Column Semantic Intent | Typical LWW Outcome | Failure Mode |
|---|---|---|
| Incremental Counter (`SUM`) | Overwrites with larger timestamp | **Lost Delta:** Prior increments are discarded completely. |
| Arithmetic Mean (`AVG`) | Discards one observation | **Sample Loss:** Statistical variance is lost; single source dominates. |
| Append Log (`APPEND`) | Overwrites entire text field | **Silent Discard:** Text entered offline by one peer disappears. |
| Immutable Invariant (`REJECT`)| Silently applies overwrite | **Safety Violation:** Critical keys or biometric values are mutated without authorization. |

These structural failure modes directly motivate the SemanticSync architecture.
