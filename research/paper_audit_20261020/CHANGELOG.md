# Changelog & Audit Reconciliations: Paper Audit 2026-10-20

## 1. Overview
This changelog details the audit reconciliations, artifact validations, and manuscript enhancements completed on 2026-10-20 for the demo paper:
`SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases`.

All deliverables are isolated within `research/paper_audit_20261020/` to ensure original research artifacts and repository baselines remain untouched.

---

## 2. Changes to Manuscript (`FINAL_DEMO_PAPER.md` & `FINAL_DEMO_PAPER.pdf`)

1. **Title & Abstract:**
   - Updated the abstract to accurately present the audited 90-trial, 9-configuration explicit-`INCREMENT` evaluation suite alongside the historical SET-based stress benchmarks.
   - Refined abstract claims to explicitly state that paired timing deltas are positive (median deltas ranging from 449.7 ms to 84,368.7 ms), reflecting mechanism overhead for metadata tracking and receipt persistence rather than computational superiority.
   - Preserved author and affiliation designations while flagging institutional department style for manual confirmation.

2. **Separation of Experiment Families:**
   - Maintained strict separation between:
     - **Historical SET-Based Stress Benchmarks** (18 trials across 9 configurations, 2 paired trials per cell; state diffing, 97.50%–98.25% SCR, with shortfall explained by equal-valued concurrent assignments).
     - **Explicit INCREMENT Evaluation Matrix** (90 trials across 9 configurations, 10 independent seeds per cell; operation-identity logging, 100.0% SCR, 100.0% RVAR).
   - Removed any conflation of exploratory single-seed pilot findings with the complete nine-cell matrix.

3. **Required Results Table (Section 6.6):**
   - Added **Table 6**, a dedicated nine-row matrix presenting the audited empirical metrics:
     - `operations`: 1,000, 5,000, and 10,000.
     - `conflict density`: 5%, 20%, and 50%.
     - `trials`: 10 independent seeds per configuration (90 trials total).
     - `SCR summary`: 100.0% (all trials) for SemanticSync and application-sum; 0.0% for LWW.
     - `RVAR summary`: 100.0% (all trials).
     - `median paired timing difference (ms)`: Derived from underlying trial records (449.7 ms to 84,368.7 ms).
     - `IQR (ms)`: Interquartile ranges computed from trial distributions (30.6 ms to 5,995.1 ms).
     - `validation status`: PASS (confirmed by `validate_increment_evaluation.py`).

4. **Performance Framing & Fair Baselines:**
   - Explicitly clarified that direct SQL `application_sum` is a narrower baseline lacking operation identities, duplicate replay suppression, conflict recovery, referential quarantine, and causal checkpointing.
   - Clarified that positive timing deltas do not constitute a performance win or general scaling law.

5. **Section 6.7 Key Findings:**
   - Updated bullet 4 to summarize the audited 90-trial suite with exact median deltas and qualified interpretations.

---

## 3. Validation & Reproducibility Scripts

- **`analyze_experiments.py`**:
  - Implemented an automated analysis script that reads the 9 configuration JSON files directly from `research/experiments/runs/increment-full-matrix-20261020-144638/`.
  - Computes all medians, quartiles, IQRs, ranges, and consistency assertions programmatically without hard-coding any values.
  - Automatically exports `AGGREGATE_RESULTS.csv` and `VALIDATION_MATRIX.csv`.

---

## 4. Unresolved Issues & Items for Manual Confirmation

1. **Author Affiliations:**
   - Authors: `Pathak Ashmit Akhilesh` and `Yash Bohra`.
   - Affiliation: `VIT Vellore`. Exact department naming and institutional formatting should be confirmed before final submission to your professor.
2. **Bibliographic References:**
   - All 22 cited works in `references.bib` and Section 12 have verified DOIs, arXiv IDs, or official project repository links. No citations were fabricated.
   - Ensure the required citation style (e.g., Springer LNCS vs. ACM) aligns with your professor's submission guidelines.
3. **Hardware & Environment Specificity:**
   - Timing measurements were captured on a Windows 11 host with Python 3.14.3 and SQLite 3.50.4. Synchronization timing on other operating systems or disk hardware will vary.
