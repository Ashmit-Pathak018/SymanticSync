# SemanticSync — Academic Publication & Manuscript Plan

**Version:** 2.0 (Reconciled)  
**Target Venues:** PaPoC (Principles and Practice of Consistency for Distributed Data), ACM SIGMOD (Demo / Industry Track), VLDB (Artifact/Research)  
**Working Title:** *SemanticSync: Declarative Schema-Level Conflict Resolution Middleware for Replicated Relational Databases*

---

## 1. Abstract Draft

Distributed, local-first, and edge-native architectures increasingly employ SQLite as an embedded client database. While Conflict-Free Replicated Data Types (CRDTs) and Hybrid Logical Clocks (HLCs) guarantee Strong Eventual Consistency (SEC), conventional relational replication engines typically resolve concurrent column mutations using Last-Write-Wins (LWW) registers. In structured data domains, LWW causes silent data loss: concurrent counter increments are overwritten, collaborative text notes are truncated, and immutable keys are modified without warning.

We present **SemanticSync**, a domain-independent synchronization middleware that allows developers to declare column-level semantic merge policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`) directly over standard SQLite schemas. SemanticSync statically validates policy-datatype compatibility, detects concurrent divergences via three-way differential inspection, and deterministically applies policy semantics during synchronization. 

The current seeded stress evidence compares LWW and SemanticSync on generated SUM traces. It reports conflict-only SCR and benchmark-row value agreement separately; the latter compares only `bench_rows.value`, not bitwise full-database state. The regenerated 3×3 results are specific to the recorded seed, host, workload, and tested schedules and do not establish general convergence. Domain workload results and stress batch timings must be reported as distinct measurements.

---

## 2. Paper Outline

### 1. Introduction
- Motivation: Rise of local-first relational applications.
- The Semantic Correctness Gap in generic CRDT registers.
- Summary of Contributions: Architecture, policy algebra, validation, and empirical harness.

### 2. Background & Related Work
- CRDT theory (Shapiro et al., 2011; Gomes et al., 2017).
- Local-first systems (Kleppmann et al., 2019; Edwards, Petricek, and van der Storm, 2023).
- Relational replication: CR-SQLite, ElectricSQL, PowerSync.
- Invariant-preserving replication (Balegas et al., 2015, 2018; Lewchenko et al., 2018).

### 3. System Architecture & Core Workflow
- Decoupling convergence mechanics from semantic resolution.
- Schema introspection via SQLite `PRAGMA table_info`.
- Causality tracking via Hybrid Logical Clocks (`_ss_change_log`).
- Three-way differential conflict detection.

### 4. Semantic Policy Framework
- Formal policy definitions: $V_{\text{resolved}} = f(V_{\text{base}}, V_A, V_B)$.
- Algebraic properties: commutativity, associativity, and idempotency boundaries.
- Pre-runtime type validation matrix.
- Flagged conflict triage (`REJECT`) and durability.

### 5. Advanced Relational Mutation Extensions (Design & Model)
- INSERT vs. INSERT collisions and primary key constraints.
- UPDATE vs. DELETE tombstone semantics.
- Referential integrity: Foreign key orphan quarantine.

### 6. Empirical Evaluation
- Experimental design and workload definitions.
- Conflict-only Semantic Correctness Rate ($SCR$), benchmark-row value agreement (RVAR), and separately measured full-state convergence where available; do not call RVAR full-database convergence.
- Latency and resolution overhead analysis.
- Threats to validity and limitations.

### 7. Conclusion & Future Work
- N-replica mesh synchronization and log compaction.
