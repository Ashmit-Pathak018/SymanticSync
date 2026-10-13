# SemanticSync — Empirical Evaluation & Experimental Design

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Experimental Methodology

The objective of the experimental harness is to test whether schema-declared semantic policies deliver higher semantic correctness than standard timestamp registers without compromising state convergence or latency.

### Scientific Integrity Principles
1. **Fair Baseline Comparison:** The baseline (Generic LWW) and the proposed system (SemanticSync) are evaluated against identical initial states, identical concurrent mutation traces, and identical timestamp distributions.
2. **Independent Ground Truth:** Expected outcomes are established a priori based on domain invariants, completely independent of resolver implementation code.
3. **Reproducibility:** Workload seeds, schema creation scripts, and mutation sequences are deterministic and version-controlled.

---

## 2. Benchmark Workloads & Conflict Scenarios

### Domain 1: Inventory & Catalog Management (`InventoryWorkload`)
- **Schema:** `products(id INTEGER PK, sku TEXT, name TEXT, quantity INTEGER, unit_price REAL, description TEXT)`
- **Policy Mapping:**
  - `quantity -> SUM` (Additive inventory adjustments)
  - `description -> APPEND` (Collaborative notes/descriptions)
  - `sku -> REJECT` (Immutable product SKU)
  - `name -> LWW` (Title updates)
  - `unit_price -> AVG` (Price compromise/averaging)

### Domain 2: Collaborative Notes & Revisions (`NotesWorkload`)
- **Schema:** `notes(id INTEGER PK, title TEXT, body TEXT, author TEXT, edit_count INTEGER, updated_at TEXT)`
- **Policy Mapping:**
  - `body -> APPEND` (Text preservation)
  - `edit_count -> SUM` (Revision counter)
  - `author -> REJECT` (Attribution invariant)
  - `title -> LWW` (Document naming)

### Domain 3: Healthcare Telemetry & Records (`HealthWorkload`)
- **Schema:** `patients(id INTEGER PK, name TEXT, blood_type TEXT, heart_rate INTEGER, dosage_mg REAL, clinical_notes TEXT)`
- **Policy Mapping:**
  - `heart_rate -> AVG` (Sensor reading reconciliation)
  - `dosage_mg -> AVG` (Dosage reconciliation)
  - `clinical_notes -> APPEND` (Preservation of observations)
  - `blood_type -> REJECT` (Safety-critical immutable key)
  - `name -> LWW` (Demographic update)

---

## 3. Evaluation Metrics

### 1. Semantic Correctness Rate ($SCR$)
$$SCR = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Result}_i = \text{GroundTruth}_i)}{N} \times 100\%$$
- **Ground Truth Match Criteria:**
  - For scalar / numeric: bitwise or arithmetic equality.
  - For text append: preservation of both contributor strings.
  - For `REJECT`: system sets status to `flagged`, leaves replica unmutated, and registers conflict record.

### 2. State Convergence Rate ($CR$)
$$CR = \frac{\sum_{k=1}^{R} \mathbb{I}(S_A^k \equiv S_B^k)}{R} \times 100\%$$
Measures whether synchronized replicas achieve bitwise state equivalence. Both Baseline and SemanticSync are required to achieve $CR = 100\%$.

### 3. Validation Rejection Accuracy ($VRA$)
Measures the system's ability to reject incompatible policy assignments before runtime (e.g., `SUM` on `TEXT` or `AVG` on `TEXT`). Required: $100\%$.

### 4. Computational Overhead ($\Delta t$)
Measures execution duration per conflict:
$$\Delta t = \frac{T_{\text{sync\_end}} - T_{\text{sync\_start}}}{N_{\text{conflicts}}} \quad (\text{microseconds / milliseconds})$$

---

## 4. Empirical Protocol: Phased Scaling Plan

```
┌────────────────────────────────────────────────────────────────────────┐
│                      BENCHMARK SCALING PHASES                          │
├─────────────────────┬──────────────────────────┬───────────────────────┤
│ Tier                │ Conflict Count           │ Purpose               │
├─────────────────────┼──────────────────────────┼───────────────────────┤
│ Tier 1 (Current)    │ 9 conflicts (3 / workload│ Unit verification     │
│ Tier 2 (Phase 4)    │ 1,000 conflicts          │ Statistical stability │
│ Tier 3 (Phase 4)    │ 10,000 conflicts         │ Latency & throughput  │
└─────────────────────┴──────────────────────────┴───────────────────────┘
```

### Tier 2 & Tier 3 Parametric Configuration
In Phase 4, synthetic trace generators will simulate:
- **Conflict Densities:** $5\%$, $20\%$, $50\%$ of total table rows.
- **Replica Topologies:** Pairwise ($N=2$) scaling to Mesh ($N=3, 5$).
- **Telemetry Collected:**
  - Latency percentiles: p50, p95, p99.
  - Throughput: conflicts resolved per second.
  - Change log expansion rate (bytes per transaction).
