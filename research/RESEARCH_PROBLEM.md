# SemanticSync — Research Problem Formulation

**Version:** 1.0  
**Authors:** SemanticSync Research Team  
**Subject:** Declarative Semantic Conflict Resolution in Distributed Relational Replicas

---

## 1. Abstract Problem

In decentralized, local-first, and multi-master relational data architectures, concurrent offline operations inherently lead to data divergence. State-based and operation-based Conflict-Free Replicated Data Types (CRDTs) guarantee Strong Eventual Consistency (SEC) across replicas by enforcing a mathematically proven join-semilattice or commutative operation graph.

However, standard CRDT primitives suffer from **semantic blindness**:
- **Last-Write-Wins (LWW)** registers resolve conflicts by ordering wall-clock or logical timestamps, inevitably discarding one replica's mutation entirely regardless of the domain intent.
- **Syntactic Merges** treat database columns as generic primitive types (scalars, strings, or registers) rather than domain quantities (e.g., inventories, cumulative counters, clinical notes, invariant identifiers).

This disparity introduces the **Semantic Correctness Deficit**: while all replicas converge to identical bitwise states (guaranteeing SEC), the converged state frequently violates user expectations, loses business operations, or corrupts domain invariants.

---

## 2. Research Questions (RQ)

- **RQ1 (Semantic Efficacy):** Can declarative, column-level semantic policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`) measurably improve the rate of domain-correct state reconciliations compared to standard LWW CRDT baselines under concurrent divergent mutations?
- **RQ2 (Determinism & Convergence):** Can a semantic resolution layer preserve the convergence guarantees (SEC) of standard CRDTs across arbitrary replica topologies without introducing nondeterministic divergence or infinite sync loops?
- **RQ3 (Computational Overhead):** What is the runtime latency and memory overhead of three-way diffing and semantic evaluation compared to pure timestamp-based register assignment during database synchronization?

---

## 3. Scope and Hypothesis

### Hypothesis
*By decoupling CRDT synchronization mechanics from column-level conflict resolution through declarative, schema-registered semantic policies, distributed SQLite replicas can achieve a significantly higher Semantic Correctness Rate ($SCR \ge 90\%$) than timestamp-based LWW registers ($SCR \le 40\%$) while maintaining deterministic state convergence and sub-millisecond per-cell resolution overhead.*

### Scope Boundaries
1. **Target Engine:** Local relational storage (SQLite 3).
2. **Conflict Granularity:** Cell-level concurrent divergence on shared primary keys (UPDATE vs. UPDATE).
3. **Topology:** Multi-replica edge devices communicating asynchronously via snapshot/log exchange.
