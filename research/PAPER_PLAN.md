# SemanticSync — Academic Publication Plan

**Target Venue:** ACM SIGMOD / VLDB / IEEE ICDE / PaPoC (Principles and Practice of Consistency for Distributed Data)  
**Track:** Research Track or Demonstration Track  
**Working Title:** *SemanticSync: Declarative Semantic Policy Middleware for Strong Eventual Consistency in Relational Replicas*

---

## 1. Paper Abstract Draft

Distributed and local-first applications increasingly deploy embedded relational databases (such as SQLite) on user edge devices. While state-based Conflict-Free Replicated Data Types (CRDTs) guarantee Strong Eventual Consistency (SEC), conventional implementations resolve concurrent mutations using semantic-blind policies such as Last-Write-Wins (LWW). In relational domains, LWW regularly causes silent data loss, corrupting counters, truncating collaborative text, and discarding critical updates.

We present **SemanticSync**, a declarative, schema-level semantic conflict resolution middleware for distributed SQLite databases. SemanticSync allows engineers to annotate columns with high-level reconciliation policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`) while enforcing strict compile-time type compatibility. Powered by a Hybrid Logical Clock (HLC) and deterministic three-way differential resolution engine, SemanticSync decouples domain intent from raw CRDT convergence. Empirical evaluation across inventory, collaborative editing, and healthcare workloads demonstrates that SemanticSync achieves a 100% Semantic Correctness Rate ($SCR$) compared to 33.3% for standard LWW, with sub-100 microsecond per-cell resolution overhead and zero convergence violations.

---

## 2. Structure & Section Outline

1. **Introduction**
   - The rise of local-first computing and edge SQLite.
   - The semantic limitation of standard CRDT registers.
   - Core contributions: declarative policy registry, type validator, deterministic resolver, and empirical benchmark harness.
2. **Background & Motivation**
   - CRDT fundamentals and the limits of LWW.
   - Motivating examples: inventory replenishment vs. clinical note updates.
3. **System Architecture**
   - Architectural topology and separation of concerns.
   - SQLite schema introspection and type normalization.
   - Hybrid Logical Clock ordering and metadata tracking.
4. **Semantic Policy Framework**
   - Policy formalisms: commutativity, determinism, and delta arithmetic.
   - Fail-fast type compatibility verification.
   - Three-way differential conflict detection.
5. **Evaluation**
   - Experimental methodology and workload construction.
   - Semantic Correctness Rate ($SCR$) evaluation.
   - Latency and convergence verification.
6. **Related Work**
   - Comparison with CR-SQLite, Automerge, Yjs, and Operational Transformation.
7. **Conclusion & Future Directions**
   - Composite keys, multi-table foreign key constraints, and P2P transport.
