# SemanticSync — Benchmark Ground Truths

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification

---

## 1. Overview & Definition

A ground-truth conflict record establishes the objectively expected domain outcome when two replicas concurrently diverge from an ancestor base snapshot:

$$\mathcal{GT} = \langle \text{table}, \text{row\_id}, \text{column}, V_{\text{base}}, V_A, V_B, \text{Policy}, V_{\text{expected\_semantic}}, V_{\text{expected\_baseline}} \rangle$$

---

## 2. Verified Test Scenarios

### Workload 1: Inventory (`InventoryWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) | Rationale |
|---|---|---|---|---|---|---|---|---|
| `1` | `quantity` | `SUM` | `100` | `115` (+15) | `120` (+20) | `135` | `120` | Additive delta merge: $100 + 15 + 20 = 135$. Baseline overwrites A's sale. |
| `1` | `description` | `APPEND` | `'Original description'` | `'Original description. Note from A.'` | `'Original description. Note from B.'` | Both notes preserved with delimiter | Only Note from B preserved | Both contributors' annotations must be preserved. Baseline truncates A. |
| `1` | `sku` | `REJECT` | `'SKU-001'` | `'SKU-UPDATED'` | `'SKU-001'` | `'FLAGGED'` | `'SKU-001'` | SKU is an invariant key. Automated overwrite is forbidden. |

---

### Workload 2: Notes (`NotesWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) | Rationale |
|---|---|---|---|---|---|---|---|---|
| `1` | `edit_count` | `SUM` | `5` | `6` (+1) | `7` (+2) | `8` | `7` | Edit counters represent independent increments: $5 + 1 + 2 = 8$. |
| `1` | `body` | `APPEND` | `'Initial draft.'` | `'Initial draft. Added section 1.'` | `'Initial draft. Added section 2.'` | Both sections preserved with delimiter | Only section 2 preserved | Preserves both authors' concurrent section additions. |
| `1` | `author` | `REJECT` | `'Author Alice'` | `'Author Bob'` | `'Author Alice'` | `'FLAGGED'` | `'Author Alice'` | Authorship attribution is immutable; conflict flagged for triage. |

---

### Workload 3: Healthcare (`HealthWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) | Rationale |
|---|---|---|---|---|---|---|---|---|
| `1` | `heart_rate` | `AVG` | `72` | `75` | `69` | `72.0` | `69` | Arithmetic mean of sensor telemetries: $(75 + 69) / 2 = 72.0$. |
| `1` | `clinical_notes`| `APPEND`| `'Admitted.'` | `'Admitted. Note from Nurse.'` | `'Admitted. Note from Doctor.'`| Both clinical observations preserved | Only Doctor note preserved | Medical observation safety: never discard nurse observation. |
| `1` | `blood_type` | `REJECT` | `'O+'` | `'AB+'` | `'O+'` | `'FLAGGED'` | `'O+'` | Blood type is life-critical invariant. Automated resolution is unsafe. |

---

## 3. Evaluation Rules for Benchmark Scorer

1. **Exact Numeric Equality:** Scalar values must match precisely ($135 = 135$, $8 = 8$, $72.0 = 72.0$).
2. **Text Containment:** For `APPEND`, the merged string must contain the unique textual additions from both replicas.
3. **Safety Flag Match:** For `REJECT`, the system must return `status = "flagged"`, `resolved_value = None`, and register the conflict in `MergeManager`. Baseline LWW never flags conflicts (it always selects a winner), so baseline score on `REJECT` scenarios is strictly $0\%$.
