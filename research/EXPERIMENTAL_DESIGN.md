# SemanticSync — Experimental Design

**Version:** 1.0

---

## 1. Experimental Setup

The evaluation framework rigorously tests whether declarative semantic policies resolve concurrent mutations in relational replicas without loss of business intent or convergence anomalies.

### Controlled Divergence Architecture
```
              [Common Ancestor / Base DB]
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      [Replica Device A]          [Replica Device B]
             │                           │
    (Controlled Mutation Δa)    (Controlled Mutation Δb)
             │                           │
             └─────────────┬─────────────┘
                           ▼
              [Sync Execution & Evaluation]
               ├── Generic LWW Engine (Baseline)
               └── SemanticSync Engine (Proposed)
```

---

## 2. Evaluated Workload Domains

We construct three diverse, realistic benchmark domains:

### 1. Inventory & Supply Chain Workload (`InventoryWorkload`)
- **Nature:** High-volume quantitative updates, textual catalog data, immutable SKU identifiers.
- **Schema:** `products(id, sku, name, quantity, unit_price, description)`
- **Target Policies:** `quantity -> SUM`, `description -> APPEND`, `sku -> REJECT`, `name -> LWW`, `unit_price -> AVG`

### 2. Collaborative Document Notes Workload (`NotesWorkload`)
- **Nature:** Rich-text note modifications, revision metrics, author verification.
- **Schema:** `notes(id, title, body, author, edit_count, updated_at)`
- **Target Policies:** `body -> APPEND`, `edit_count -> SUM`, `author -> REJECT`, `title -> LWW`

### 3. Patient Health Metrics Workload (`HealthWorkload`)
- **Nature:** Safety-critical sensor telemetries, patient identifiers, doctor clinical notes.
- **Schema:** `patients(id, name, blood_type, heart_rate, dosage_mg, clinical_notes)`
- **Target Policies:** `heart_rate -> AVG`, `dosage_mg -> AVG`, `clinical_notes -> APPEND`, `blood_type -> REJECT`, `name -> LWW`

---

## 3. Conflict Injection Protocol

For each workload, three deterministic conflict scenarios are systematically generated:
1. **Additive/Counter Divergence:** Independent scalar additions against baseline values.
2. **Textual/Cumulative Divergence:** Independent textual updates intended to preserve collaborative inputs.
3. **Safety-Critical / Immutable Divergence:** Uncoordinated attempts to modify immutable identifiers or invariant attributes.

---

## 4. Evaluation Procedure

1. **Instantiation:** Generate base SQLite database with known seed fixtures.
2. **Forking:** Instantiate identical replicas $R_A$ and $R_B$ with active `_ss_change_log` tables.
3. **Mutation:** Apply divergent mutations $M_A$ and $M_B$ at controlled HLC timestamps ($T_A < T_B$).
4. **Baseline Execution:** Execute timestamp-ordered Last-Write-Wins merge.
5. **Semantic Execution:** Execute SemanticSync `CRDTSyncEngine.sync_replicas()` with registered policies.
6. **Comparison & Verification:**
   - Verify state convergence: $R_A \equiv R_B$.
   - Compare converged values against predetermined ground-truth expectations.
   - Record convergence status, Semantic Correctness Rate ($SCR$), and resolution execution time ($\mu s$).
