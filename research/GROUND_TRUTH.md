# SemanticSync — Ground Truth Conflict Specifications

**Version:** 1.0

---

## 1. Overview

To evaluate synchronization algorithms scientifically, ground truth must be explicitly predefined. A ground-truth tuple is defined as:

$$\mathcal{GT} = \langle T, R_{id}, C, V_{\text{base}}, V_A, V_B, V_{\text{expected\_semantic}}, V_{\text{expected\_baseline}} \rangle$$

Where:
- $T$: Table name
- $R_{id}$: Target row primary key
- $C$: Target column name
- $V_{\text{base}}$: Common ancestor value
- $V_A, V_B$: Divergent replica mutations
- $V_{\text{expected\_semantic}}$: The semantically correct outcome
- $V_{\text{expected\_baseline}}$: Standard Last-Write-Wins outcome ($V_B$ assuming $T_B > T_A$)

---

## 2. Workload Ground Truth Tables

### Workload 1: Inventory (`InventoryWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) |
|---|---|---|---|---|---|---|---|
| `1` | `quantity` | `SUM` | `100` | `115` (+15) | `120` (+20) | `135` | `120` *(Data Loss: -15)* |
| `1` | `description` | `APPEND` | `'Original description'` | `'Original description. Note from A.'` | `'Original description. Note from B.'` | Concatenated both contributions | `'Original description. Note from B.'` *(Overwrite)* |
| `1` | `sku` | `REJECT` | `'SKU-001'` | `'SKU-UPDATED'` | `'SKU-001'` | `'FLAGGED'` *(Manual Review Required)* | `'SKU-001'` *(Silently overwritten)* |

---

### Workload 2: Collaborative Notes (`NotesWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) |
|---|---|---|---|---|---|---|---|
| `1` | `edit_count` | `SUM` | `5` | `6` (+1) | `7` (+2) | `8` | `7` *(Lost edit tick)* |
| `1` | `body` | `APPEND` | `'Initial draft.'` | `'Initial draft. Added section 1.'` | `'Initial draft. Added section 2.'` | Both sections preserved with delimiter | Only section 2 preserved |
| `1` | `author` | `REJECT` | `'Author Alice'` | `'Author Bob'` | `'Author Alice'` | `'FLAGGED'` | `'Author Alice'` |

---

### Workload 3: Healthcare Telemetry (`HealthWorkload`)

| Row ID | Column | Policy | Base Value ($V_{\text{base}}$) | Replica A ($V_A$) | Replica B ($V_B$) | Expected Semantic ($V_{\text{semantic}}$) | Expected Baseline ($V_{\text{baseline}}$) |
|---|---|---|---|---|---|---|---|
| `1` | `heart_rate` | `AVG` | `72` | `75` | `69` | `72.0` | `69` *(Arbitrary sensor pick)* |
| `1` | `clinical_notes`| `APPEND`| `'Admitted.'` | `'Admitted. Note from Nurse.'` | `'Admitted. Note from Doctor.'`| Concatenated clinical remarks | Only Doctor note preserved |
| `1` | `blood_type` | `REJECT` | `'O+'` | `'AB+'` | `'O+'` | `'FLAGGED'` *(Safety stop)* | `'O+'` |

---

## 3. Scoring Rules for Evaluation

1. **Value Match:** A resolution is marked correct if and only if $\text{result} = V_{\text{expected}}$.
2. **Safety Stop Handling (`REJECT`):** For safety-critical columns governed by `REJECT`, a resolution is deemed correct if the system sets status to `'flagged'`, assigns no automated mutation, and registers the conflict for human triage (`"FLAGGED"` token in evaluation scoring).
