# SemanticSync — Literature Review & Theoretical Context

**Version:** 2.0 (Reconciled)  
**Field:** Distributed Computing (`cs.DC`), Database Systems (`cs.DB`)

---

## 1. Verified Foundational Literature

### Conflict-Free Replicated Data Types (CRDTs)
- **Shapiro et al. (2011)** — *Conflict-free replicated data types* (SSS 2011).
  - *Contribution:* Formulated State-based (CvRDT) and Operation-based (CmRDT) systems. Proved that monotonic join-semilattices $\langle S, \sqcup \rangle$ guarantee Strong Eventual Consistency (SEC) across partial orders.
  - *Connection to SemanticSync:* Standard LWW registers are join-semilattices over $(\text{timestamp}, \text{value})$ tuples. However, when applied to relational attributes (such as counters or texts), the LWW semilattice ordering ignores operation deltas.
- **Gomes, Kleppmann, et al. (2017)** — *Verifying Strong Eventual Consistency in Distributed Systems* (OOPSLA 2017 / [arXiv:1707.01747](https://arxiv.org/abs/1707.01747)).
  - *Contribution:* Machine-checked verification of CRDT convergence (RGA, OR-Set, PN-Counter) in Isabelle/HOL. Established an axiomatic network model capturing message delivery anomalies.
  - *Relevance to SemanticSync:* Informs our verification strategy. For SemanticSync policies to guarantee SEC, each operator must be rigorously analyzed for commutativity and associativity over historical operations.

### Causality and Hybrid Logical Clocks
- **Kulkarni et al. (2014)** — *Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases*.
  - *Contribution:* Formulated the Hybrid Logical Clock (HLC). Bounded logical clock progression by wall-clock drift while preserving monotonic causal ordering.
  - *Application:* Used in SemanticSync (`backend/engine/crdt_sync.py`) to provide deterministic causality tracking across distributed SQLite replicas.

### Local-First Relational Systems & Extensions
- **Kleppmann et al. (2019)** — *Local-first software: you own your data, in spite of the cloud* (Onward! 2019).
  - *Contribution:* Defined the seven architectural ideals of local-first software.
- **Marr et al. (2023)** — *Live & Local Schema Change: Challenge Problems* ([arXiv:2309.11406](https://arxiv.org/abs/2309.11406)).
  - *Contribution:* Outlined open challenges in local-first database replication: schema migration drift, foreign key orphanages, and cross-row constraint preservation.
- **CR-SQLite (vlcn.io) / ElectricSQL / PowerSync:**
  - *Current Landscape:* CR-SQLite implements a C-extension for SQLite embedding LWW-per-column and fractional indexing via a delta-table (`crsql_changes`). ElectricSQL and PowerSync use central Postgres engines with logical replication to manage partial SQLite sync.
  - *Differentiation:* Most existing relational replication engines default to column-level LWW or server-mediated transactions. SemanticSync investigates declarative, type-validated semantic policies (`SUM`, `AVG`, `APPEND`, `REJECT`) executed directly over native SQLite without specialized external services.

---

## 2. Invariant-Preserving Replication Literature

A critical research area is preserving relational and numeric constraints under weak consistency:

- **Balegas et al. (2018)** — *IPA: Invariant-preserving Applications for Weakly-consistent Replicated Databases* ([arXiv:1802.08474](https://arxiv.org/abs/1802.08474)).
  - *Contribution:* Static analysis and runtime repair actions to uphold application correctness under weak consistency without full coordination.
  - *Relevance:* Supports SemanticSync's strategy of explicit conflict flagging (`REJECT`) and orphan quarantine rather than silent corruption.
- **Balegas et al. (2015)** — *Extending Eventually Consistent Cloud Databases for Enforcing Numeric Invariants* ([arXiv:1503.09052](https://arxiv.org/abs/1503.09052)).
  - *Contribution:* Bounded counters using escrow techniques to prevent numeric underflow (e.g., negative inventory or negative balance) under eventual consistency.
  - *Connection to SemanticSync:* Demonstrates that naive additive `SUM` ($base + \Delta A + \Delta B$) is unsafe under negative deltas without explicit boundary enforcement.
- **Lewchenko et al. (2018)** — *Conflict-Aware Replicated Data Types (CARDs)* ([arXiv:1802.08733](https://arxiv.org/abs/1802.08733)).
  - *Contribution:* CARDs use consistency guards (two-state predicates) to determine whether concurrent operations can proceed or must be flagged/blocked.

---

## 3. Comparison Matrix: State of the Art vs. SemanticSync

| Dimension | Generic LWW CRDT | CR-SQLite | ElectricSQL | SemanticSync (This Project) |
|---|---|---|---|---|
| **Underlying Engine** | Key-Value / Object | SQLite (C Ext) | Postgres ↔ SQLite | Standard SQLite (`sqlite3`) |
| **Convergence Mechanism** | HLC / Vector Clocks | Fractional Index / LWW | Logical Replication stream | HLC + 3-Way Diff Log |
| **Merge Granularity** | Register (Scalar) | Column-level LWW | Table / Row stream | Schema Column Policy |
| **Arithmetic Merges (`SUM`, `AVG`)** | ❌ (Overwrites) | ❌ (Overwrites) | ❌ (Server rules) | ✅ Declarative middleware |
| **Text Merge (`APPEND`)** | ❌ (Overwrites) | ❌ (Overwrites) | ❌ (Overwrites) | ✅ Deterministic delimiter merge |
| **Type Compatibility Validation**| ❌ None | ⚠️ Basic SQL affinity | ⚠️ Schema compilation | ✅ Pre-runtime `422` validator |
| **Safety Invariant (`REJECT`)** | ❌ (Silent win) | ❌ (Silent win) | ⚠️ Transaction failure | ✅ Durable triage record |
| **Multi-Table FK Quarantine** | ❌ (Orphan failure)| ⚠️ Cascades / Ignores | ✅ Server-enforced | 📋 Phased implementation |
