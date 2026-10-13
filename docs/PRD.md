# SemanticSync — Product Requirements Document (PRD)

**Version:** 2.0 (Reconciled)  
**Status:** Approved Technical Specification  
**Last Updated:** October 2026

---

## 1. Product Vision & Problem Statement

Distributed, local-first applications built on SQLite face an unsolved challenge: when independent offline replicas modify the same record, how should conflicting values be reconciled?

Generic CRDT solutions solve **convergence** (ensuring all replicas eventually hold identical bytes), but they fail on **semantic correctness**. A Last-Write-Wins (LWW) register blindly overwrites additive counters (e.g., inventory depletions) and truncates collaborative notes.

**SemanticSync is a declarative semantic synchronization middleware for replicated SQLite databases.** It allows developers to annotate relational columns with declarative merge policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`) that preserve business intent during reconciliation, while keeping standard SQL queries and local SQLite engines completely unchanged.

---

## 2. Core Pillars & Architectural Principles

1. **Standard SQLite & Plain SQL:** No proprietary database dialect. Applications continue using standard SQLite connections.
2. **Domain-Independent Engine:** Core algorithms in `backend/engine/` operate exclusively on schema datatypes and explicit policy configurations. Zero business logic is hardcoded.
3. **Fail-Fast Type Validation:** Incompatible policies (such as `AVG` on `TEXT`) are rejected with `HTTP 422` before runtime execution.
4. **Deterministic Convergence:** Every policy operator is deterministic. Given identical inputs, all replicas compute identical outputs.
5. **Safety by Default:** When automated resolution cannot be proven safe, the conflict is preserved in an unmerged `flagged` state for human review (`REJECT` policy).

---

## 3. Phased Product Scope

### Phase 1: Core Correctness & Audit (Current Baseline)
- Schema inspection via SQLite PRAGMAs (`INTEGER`, `REAL`, `TEXT`, `BLOB`, `NUMERIC`).
- Policy validation with HTTP 422 error codes.
- Deterministic 3-way cell-level resolution for UPDATE vs. UPDATE.
- Pairwise HLC synchronization between two replicas.
- FastAPI REST backend and React/Vite SemanticSync Studio.

### Phase 2: Full Row-Mutation Conflict Model
- Detection and resolution of `INSERT vs INSERT` (PK & UNIQUE collisions).
- Detection and resolution of `UPDATE vs DELETE` (Tombstone policies).
- Safe handling of `DELETE vs DELETE` (Idempotent convergence).
- Conflict durability and recovery.

### Phase 3: Invariant Preservation & N-Replica Topologies
- Implementation of `BOUNDED_SUM` policy with floor/ceiling invariant checks.
- Verification of convergence across $N \ge 3$ replicas with varying synchronization orderings.

### Phase 4: Scaled Empirical Benchmark Suite
- Parameterized stress harness scaling from 9 scenarios to 1,000–10,000 operations.
- Configurable conflict densities ($5\%, 20\%, 50\%$).
- Automated computation and export of SCR, CR, p50/p95/p99 latency, and resolution overhead.

### Phase 5: Relational Foreign Key Integrity
- Foreign-key orphan detection when parent rows are deleted while child rows are updated.
- Non-destructive `_ss_quarantine` table routing to preserve database integrity.

### Phase 6: Operational Log Compaction
- Causal stability checkpointing to prune `_ss_change_log` without data loss.

### Phase 7: Research Release & Studio Polish
- Telemetry integration in Studio Analytics view, complete documentation package, and research manuscript.
