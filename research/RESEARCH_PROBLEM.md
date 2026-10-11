# SemanticSync — Research Problem Formulation

**Version:** 2.0 (Reconciled)  
**Status:** Implementation-Ready Specification  
**Field:** Distributed Systems, Local-First Software, Replicated Relational Middleware

---

## 1. Problem Formulation

Distributed, edge, and local-first software architectures increasingly store application state in embedded relational databases, predominantly SQLite. When autonomous replicas perform disconnected local mutations, replicas diverge.

Conflict-Free Replicated Data Types (CRDTs) provide mathematical foundations for Strong Eventual Consistency (SEC): given identical sets of mutations delivered across replicas, replicas converge to bitwise-identical states without distributed consensus.

However, generic state-based and operation-based CRDT registers deployed in production typically operate with **semantic blindness**:
- **Last-Write-Wins (LWW) Registers:** Select a winning value based on physical wall-clock timestamps or logical counters. In relational tables, this discards concurrent additive increments (e.g., inventory depletions or ledger increments), truncates collaborative textual annotations, and silently overwrites invariant keys.
- **Syntactic Multi-Value Registers (MVR):** Retain conflicting values as a set, deferring resolution to the application layer. In structured relational schemas with typed columns and constraints (`NOT NULL`, `CHECK`, `FOREIGN KEY`), unconstrained value sets break relational invariants.

### The Research Question

> **Can schema-level, domain-independent semantic policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`) be integrated into a relational synchronization middleware over SQLite such that: (1) semantic correctness under concurrent divergence is measurably improved over generic LWW registers, (2) deterministic convergence is maintained under specified assumptions, and (3) foreign-key and row-level invariants are preserved without full two-phase commit?**

---

## 2. Research Scope & Boundaries of Contribution

### What SemanticSync Contributes
1. **Schema-Level Policy Integration:** Explicit, declarative column-level merge policies mapped to standard SQLite schemas and validated for datatype compatibility prior to runtime execution.
2. **Deterministic Reconciliation Semantics:** Formal specification of state requirements, operation histories, and exact merge operators for each policy.
3. **Reproducible Comparative Evaluation:** An empirical evaluation harness measuring Semantic Correctness Rate ($SCR$), state convergence, validation accuracy, and overhead against a controlled baseline.
4. **Relational Conflict Taxonomy:** A structured classification of relational mutation conflicts beyond simple update divergence (including insert collisions, update vs. delete, and foreign key orphans).

### What SemanticSync Does NOT Claim to Invent
- **CRDTs:** Invented by Shapiro et al. (2011). SemanticSync uses CRDT and HLC mechanisms where applicable.
- **Local-First Software:** Conceptualized by Kleppmann et al. (2019).
- **Per-Field Merging:** Prior systems (e.g., Lotus Notes, CouchDB, Git) have merged fields; SemanticSync formalizes schema-declared semantics for relational replicas.
- **General Consensus:** SemanticSync operates within asynchronous, coordination-free replication models; it does not replace Paxos/Raft for linearizable transactions.

---

## 3. Concrete Research Hypotheses

- **H1 (Semantic Accuracy):** On workloads exhibiting additive, cumulative, or invariant-guarded concurrent updates, declarative semantic policies achieve an $SCR \ge 90\%$ against predefined ground truths, compared to $\le 40\%$ for pure LWW registers.
- **H2 (Convergence Preservation):** For all policies satisfying commutativity, associativity, and idempotency (or evaluated with deterministic tie-breaking over causal histories), multi-replica convergence ($CR$) remains strictly $100\%$.
- **H3 (Minimal Overhead):** Three-way differential detection and policy evaluation introduce sub-millisecond per-cell resolution overhead, representing less than $5\%$ of local SQLite transaction commit latency.
