# SemanticSync — Results Protocol & Empirical Telemetry

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Distinguishing Measured Results vs. Future Targets

To maintain strict scientific integrity in the documentation:

| Status Tag | Meaning |
|---|---|
| **[Measured]** | Empirically verified on the current codebase via automated unit/benchmark tests. |
| **[Target]** | Planned research objective for scaled workloads ($N \ge 1,000$). |

---

## 2. Currently Measured Empirical Results (Tier 1: 9 Scenarios)

The following metrics reflect verified execution on the current prototype across the 3 standard workloads:

| Workload Domain | Conflict Count | Baseline LWW SCR (%) [Measured] | SemanticSync SCR (%) [Measured] | Convergence Rate (%) [Measured] | Overhead / Conflict [Measured] |
|---|---|---|---|---|---|
| **Inventory** | 3 | **33.3%** (1/3) | **100.0%** (3/3) | 100.0% | ~0.05 ms |
| **Notes** | 3 | **33.3%** (1/3) | **100.0%** (3/3) | 100.0% | ~0.04 ms |
| **Healthcare** | 3 | **33.3%** (1/3) | **100.0%** (3/3) | 100.0% | ~0.05 ms |
| **Aggregate Mean** | **9** | **33.3%** | **100.0%** | **100.0%** | **< 0.1 ms** |

### Verified Observations:
1. On each workload, exactly one scenario is correctly resolved by LWW (the scenario where simple recency is the intended policy).
2. The remaining two scenarios per workload (`SUM` delta and `APPEND` preservation) fail under LWW, yielding exactly 33.3% SCR.
3. SemanticSync correctly resolves all 3 scenarios per workload (including flagging `REJECT` cases), yielding 100.0% SCR.

---

## 3. Scaled Benchmark Targets (Tier 2 & 3: Phase 4)

The planned Phase 4 benchmark harness will execute parameterized stress runs with the following targets:

| Workload Size | Conflict Density | Target Baseline SCR | Target SemanticSync SCR | Target p95 Latency |
|---|---|---|---|---|
| **1,000 Operations** | 5% | $\le 35.0\%$ | $\ge 95.0\%$ | $< 0.5\text{ ms}$ |
| **1,000 Operations** | 20% | $\le 35.0\%$ | $\ge 95.0\%$ | $< 0.8\text{ ms}$ |
| **10,000 Operations**| 50% | $\le 35.0\%$ | $\ge 90.0\%$ | $< 1.5\text{ ms}$ |

---

## 4. Reproducible Execution Protocol

To reproduce the measured Tier 1 results:

```bash
# 1. Run unit test suite
python -m pytest backend/tests/test_benchmark.py -v

# 2. Execute live API benchmark endpoints
curl -s -X POST http://127.0.0.1:8000/api/v1/benchmark/run -H "Content-Type: application/json" -d '{"workload": "inventory"}'
curl -s -X POST http://127.0.0.1:8000/api/v1/benchmark/run -H "Content-Type: application/json" -d '{"workload": "notes"}'
curl -s -X POST http://127.0.0.1:8000/api/v1/benchmark/run -H "Content-Type: application/json" -d '{"workload": "health"}'
```
