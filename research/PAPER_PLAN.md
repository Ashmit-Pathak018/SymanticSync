# SemanticSync — Academic Publication & Manuscript Plan

**Version:** 2.0 (Reconciled)  
**Target Venues:** PaPoC (Principles and Practice of Consistency for Distributed Data), ACM SIGMOD (Demo / Industry Track), VLDB (Artifact/Research)  
**Working Title:** *SemanticSync: Declarative Schema-Level Conflict Resolution Middleware for Replicated Relational Databases*

---

## 1. Abstract Draft

Distributed, local-first, and edge-native architectures increasingly employ SQLite as an embedded client database. While Conflict-Free Replicated Data Types (CRDTs) and Hybrid Logical Clocks (HLCs) guarantee Strong Eventual Consistency (SEC), conventional relational replication engines typically resolve concurrent column mutations using Last-Write-Wins (LWW) registers. In structured data domains, LWW causes silent data loss: concurrent counter increments are overwritten, collaborative text notes are truncated, and immutable keys are modified without warning.

We present **SemanticSync**, a domain-independent synchronization middleware that allows developers to declare column-level semantic merge policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`) directly over standard SQLite schemas. SemanticSync statically validates policy-datatype compatibility, detects concurrent divergences via three-way differential inspection, and deterministically applies policy semantics during synchronization. 

We evaluate SemanticSync against a generic LWW baseline across inventory, collaborative editing, and healthcare workloads. In initial empirical evaluations across representative conflict scenarios, SemanticSync achieves a 100% Semantic Correctness Rate ($SCR$) compared to 33.3% for the generic baseline, maintaining bitwise convergence and sub-millisecond resolution overhead. We outline an expanded conflict model incorporating tombstones, duplicate insert handling, and foreign key orphan quarantine.

---

## 2. Paper Outline

### 1. Introduction
- Motivation: Rise of local-first relational applications.
- The Semantic Correctness Gap in generic CRDT registers.
- Summary of Contributions: Architecture, policy algebra, validation, and empirical harness.

### 2. Background & Related Work
- CRDT theory (Shapiro et al., 2011; Gomes et al., 2017).
- Local-first systems (Kleppmann et al., 2019; Marr et al., 2023).
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
- Semantic Correctness Rate ($SCR$) and Convergence ($CR$) results.
- Latency and resolution overhead analysis.
- Threats to validity and limitations.

### 7. Conclusion & Future Work
- N-replica mesh synchronization and log compaction.
