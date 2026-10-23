# SemanticSync — Research Analysis & Expansion Plan (Post-arXiv Survey)

**Date:** October 2026  
**Methodology:** Survey of state-of-the-art literature via arXiv (Distributed Computing `cs.DC`, Databases `cs.DB`).

---

## 1. Surveyed arXiv Literature & Strategic Insights

We conducted a literature search on arXiv across CRDTs, relational replication, and invariant-preserving local-first architectures:

1. **Gomes, Kleppmann, et al. (2017) — *Verifying Strong Eventual Consistency in Distributed Systems*** ([arXiv:1707.01747](https://arxiv.org/abs/1707.01747))
   - *Key takeaway:* SEC must be formally modeled with network-aware convergence predicates.
   - *Application to SemanticSync:* We can mathematically formalize our (HLC + Semantic Policy) merge operator as a bounded semi-lattice.
2. **Balegas, Preguiça, et al. (2018) — *IPA: Invariant-preserving Applications for Weakly-consistent Replicated Databases*** ([arXiv:1802.08474](https://arxiv.org/abs/1802.08474))
   - *Key takeaway:* Weak consistency breaks relational invariants. Rather than blocking, the system should allow developers to declare repair semantics or consistency guards.
   - *Application to SemanticSync:* Directly supports our thesis. We can extend SemanticSync from single-cell policies to **Relational Invariant Policies** (e.g., non-negative bounds `quantity >= 0`, foreign key orphan isolation).
3. **Balegas et al. (2015) — *Extending Eventually Consistent Cloud Databases for Enforcing Numeric Invariants*** ([arXiv:1503.09052](https://arxiv.org/abs/1503.09052))
   - *Key takeaway:* Additive counters (`SUM`) in inventory fail when concurrent deductions exceed total stock (underflow). Escrow/bounded counters prevent negative quantities without full 2PC.
   - *Application to SemanticSync:* Introduce a `BOUNDED_SUM` policy enforcing `min_bound=0`.
4. **Lewchenko, Radhakrishna, et al. (2018) — *Conflict-Aware Replicated Data Types (CARDs)*** ([arXiv:1802.08733](https://arxiv.org/abs/1802.08733))
   - *Key takeaway:* Operations can be guarded by two-state predicates that allow local execution while inferring conflicts algorithmically.
   - *Application to SemanticSync:* Policy validators can check preconditions (e.g. valid status transitions: `DRAFT -> PUBLISHED` vs `ARCHIVED`).
5. **Ravishankar, Kulkarni, and Vaidya (2025) — *MuFASA: Asynchronous Checkpoint for Weakly Consistent Fully Replicated Databases*** ([arXiv:2510.06404](https://arxiv.org/abs/2510.06404))
   - *Key takeaway:* Proposes size-minimal asynchronous checkpointing for fully replicated weakly consistent databases.
   - *Relevance to SemanticSync:* Related checkpointing research; its model and guarantees are distinct from SemanticSync's SQLite change-log compaction and do not establish SemanticSync's correctness.
6. **Edwards, Petricek, and van der Storm (2023) — *Live & Local Schema Change: Challenge Problems*** ([arXiv:2309.11406](https://arxiv.org/abs/2309.11406))
   - *Key takeaway:* Local-first software must handle schema evolution across replicas that upgrade at different times.

---

## 2. The 4 Breakthrough Features to Implement

Based on literature gaps, here is the concrete expansion roadmap for SemanticSync:

### Feature 1: The Bounded Counter Policy (`BOUNDED_SUM`)
- **Problem:** When Replica A sells 60 items and Replica B sells 50 items from stock of 100, standard additive `SUM` yields `100 - 60 - 50 = -10`.
- **Solution:** `BOUNDED_SUM` policy with floor/ceiling checks (`min_val=0`). If violated, flag as safety conflict or allocate by escrow proportional to timestamps.

### Feature 2: Relational Invariant & Orphan Quarantine (Foreign Key Handling)
- **Problem:** Replica A deletes parent record `orders[id=10]`. Replica B updates `order_items[id=99, order_id=10]`.
- **Solution:** Introduce `FK_ORPHAN_POLICY`:
  - `RESURRECT_PARENT`: Recreates parent with minimal stub.
  - `QUARANTINE_CHILD`: Moves the child row to a `_ss_quarantine` table for user resolution, preventing SQLite foreign key crash.

### Feature 3: Full Mutation Support (`INSERT` Collisions & `UPDATE vs DELETE`)
- **Problem:** Currently only `UPDATE vs UPDATE` is handled.
- **Solution:**
  - `INSERT vs INSERT` (duplicate PK): Apply synthetic policy or auto-UUID rekeying.
  - `UPDATE vs DELETE`: Introduce `TOMBSTONE_POLICY` (`DELETE_WINS` vs `UPDATE_RESURRECTS`).

### Feature 4: Automated Large-Scale Benchmark Stress-Harness ($N=1000$ Conflicts)
- Generate a parameterized benchmark with 1,000 to 10,000 synthetic operations across configurable conflict densities (5%, 20%, 50%).
- Real-time chart telemetry into the Studio UI (`Analytics.jsx`).
