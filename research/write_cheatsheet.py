from pathlib import Path

cheatsheet_content = r"""# SemanticSync — Faculty Presentation Quick-Reference Cheatsheet

**Project:** SemanticSync: Schema-Level Semantic Merge Policies for Local-First Relational Databases  
**Authors:** Pathak Ashmit Akhilesh and Yash Bohra  
**Institution:** Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore  
**Format:** 1-Page Quick Reference Sheet for Presentation & Faculty Defense  

---

## 1. Thirty-Second Elevator Pitch

> *"Good morning, professors. Traditional local-first replication relies on syntactic policies like Last-Writer-Wins (LWW) to guarantee convergence. But on relational databases, LWW routinely destroys domain intent: two offline cashiers selling 15 and 20 items will have one sale erased, and deleting a customer while another device logs an order causes database-crashing foreign-key violations. We built **SemanticSync**, a middleware for SQLite that attaches declarative, domain-aware merge policies—like arithmetic `SUM`, `BOUNDED_SUM`, and `AVG`—directly to schema columns, tracks numeric increments with immutable operation receipts, and quarantines orphaned relational records atomically under active `PRAGMA foreign_keys = ON`. In our 90-trial evaluation matrix across up to 10,000 operations, SemanticSync achieved 100% semantic correctness against an arithmetic oracle where LWW scored 0%."*

---

## 2. Five Key Contributions

1. **Schema-Assigned Semantic Policies:** Column-level declarative policies (`SUM`, `AVG`, `APPEND`, `MIN`, `MAX`, `LWW`, `REJECT`, `BOUNDED_SUM`) replacing blunt row-level LWW.
2. **Explicit Increment Tracking:** Additive deltas tracked via immutable operation receipts (`origin_id`, `depends_on`), preventing duplicate applications during multi-pass reconciliations.
3. **Hybrid Logical Clock (HLC):** Strict causal happens-before ordering without synchronized wall clocks, derived via an exact 4-case update algorithm.
4. **Atomic Foreign-Key Quarantine:** Non-destructive preservation of orphaned child rows in `_ss_quarantine` under active `PRAGMA foreign_keys = ON`.
5. **Checkpoint-Assisted Log Compaction:** Prunes operation logs older than the global stable horizon ($H_{\text{stable}}$) with cryptographic payload hashing.

---

## 3. One-Minute Architecture Breakdown

- **SchemaInspector:** Extracts tables, columns, affinities, and constraints using SQLite pragmas.
- **PolicyRegistry & Validator:** Type-compatibility gates preventing invalid assignments (e.g., `SUM` on `TEXT`).
- **ConflictDetector:** 3-way divergence detection comparing ancestor base with replicas $A$ and $B$.
- **SemanticResolver:** Deterministic resolution core executing mathematical and string transforms.
- **FKQuarantineEngine:** Discovers inbound FKs and atomically extracts orphans into `_ss_quarantine`.
- **CRDTSyncEngine:** Coordinates pairwise sync, HLC ticks, change logging, writebacks, and compaction.

---

## 4. The Core Concrete Example: SET vs. INCREMENT

- **Ancestor Base:** Table `inventory`, Row `item_id=1`, `quantity = 100`.
- **Offline Cashier A:** Sells 15 units $\to$ `UPDATE inventory SET quantity = 85` (Physical time $t_A = 10.0$).
- **Offline Cashier B:** Sells 20 units $\to$ `UPDATE inventory SET quantity = 80` (Physical time $t_B = 15.0$).
- **Syntactic LWW Replay:** Clock $t_B > t_A \implies$ **Quantity = 80**. **15 sold items are erased.** (0% semantic correctness).
- **SemanticSync Replay (`SUM`):** Reconstructs deltas $\Delta_A = -15, \Delta_B = -20 \implies 100 + (-15) + (-20) = \mathbf{65}$. Both sales preserved! (100% semantic correctness).

---

## 5. Ten Most Likely Faculty Questions & Short Bullet Answers

1. **Why not standard CRDTs (PNCounter)?**  
   Standard CRDTs require specialized non-relational data types that bloat storage, break arbitrary SQL queries (`WHERE age > 21`), and cannot enforce foreign keys. SemanticSync brings CRDT semantics directly to native SQLite columns.
2. **Why not Raft or Paxos?**  
   Raft/Paxos require quorum majority ($> 50\%$) and halt when nodes are offline. Local-first systems must remain 100% available offline, reconciling asynchronously upon reconnection.
3. **What happens with 3+ replicas?**  
   Commutative policies (`SUM`, `MIN`, `MAX`, `BOUNDED_SUM`) converge identically regardless of pairwise reconciliation order, aided by deduplicated `origin_id` receipts. Non-associative policies (`AVG`) are documented as pairwise only.
4. **Can `SUM` produce negative numbers?**  
   Yes, if unbounded. That is why we designed `BOUNDED_SUM[min, max]`, which clamps deltas or flags out-of-bound conflicts for human review.
5. **How are foreign keys protected?**  
   `FKQuarantineEngine` detects referencing child rows, serializes them into `_ss_quarantine`, and removes them *before* deleting the parent, keeping `PRAGMA foreign_keys = ON` throughout.
6. **What happens on crash mid-sync?**  
   All changes, logs, and quarantines are wrapped in an explicit SQLite transaction. If power fails, SQLite's WAL journal automatically rolls back to a clean state on reboot.
7. **Why was latency higher than LWW?**  
   LWW only compares two numbers and overwrites. SemanticSync does real distributed database work: delta math, receipt validation, receipt deduplication, and FK integrity checks.
8. **How does log compaction avoid replaying stale deltas?**  
   Compaction retains cryptographic hashes and `origin_id` receipts in `_ss_compacted_receipts`. Any replayed delta matching an archived origin is instantly dropped.
9. **How do you handle delete-insert races?**  
   If Replica A deletes a parent while Replica B inserts a child, the child is moved to quarantine, keeping the database valid while alerting developers in `_ss_quarantine`.
10. **What is the scope of your claims?**  
    We claim deterministic schema-level pairwise merge policies, explicit increment tracking, and relational quarantine for SQLite—we do *not* claim general $N$-way mesh Byzantine consensus.

---

## 6. Essential Terminal Commands

### Terminal 1: Start Backend (Isolated Data Directory)
```powershell
$env:SEMANTICSYNC_DATA_DIR = Join-Path $env:TEMP ("SemanticSync-Demo-" + [guid]::NewGuid().ToString("N"))
py -3.14 main.py --no-reload
```

### Terminal 2: Start Studio Frontend
```powershell
cd frontend
npm run dev
```

### Run Automated Test Suite (336 Tests, 100% Pass)
```powershell
py -3.14 -m pytest backend/tests/ -q
```

### Verify Backend Health
```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

---

## 7. Key File Locations & Navigation Links

| Asset | File Path |
| :--- | :--- |
| **Compiled IEEE Paper (PDF)** | [`docs/manuscript_latex/IEEE_DEMO_PAPER.pdf`](manuscript_latex/IEEE_DEMO_PAPER.pdf) |
| **IEEE Paper Source (LaTeX)** | [`docs/manuscript_latex/IEEE_DEMO_PAPER.tex`](manuscript_latex/IEEE_DEMO_PAPER.tex) |
| **Detailed Technical Compendium** | [`docs/TECHNICAL_EXPLANATION.md`](TECHNICAL_EXPLANATION.md) |
| **Live Demonstration Guide** | [`docs/DEMO_GUIDE.md`](DEMO_GUIDE.md) |
| **Claim-to-Evidence Audit** | [`docs/CLAIM_EVIDENCE_AUDIT.md`](CLAIM_EVIDENCE_AUDIT.md) |
| **Research Literature Index** | [`papers/README.md`](../papers/README.md) |
| **Core Synchronization Engine** | [`backend/engine/crdt_sync.py`](../backend/engine/crdt_sync.py) |
| **Foreign-Key Quarantine Engine**| [`backend/engine/fk_quarantine.py`](../backend/engine/fk_quarantine.py) |
| **Compaction & Checkpoint Store** | [`backend/engine/log_compaction.py`](../backend/engine/log_compaction.py) |
| **Evaluation Matrix Artifacts** | `research/experiments/runs/increment-full-matrix-20261020-144638/` |
"""

Path('docs/PRESENTATION_CHEATSHEET.md').write_text(cheatsheet_content, encoding='utf-8')
print('Successfully written comprehensive docs/PRESENTATION_CHEATSHEET.md!')
