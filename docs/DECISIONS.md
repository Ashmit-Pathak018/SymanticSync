# SemanticSync — Architecture Decision Records (ADRs)

**Version:** 2.0 (Reconciled)  
**Status:** Active Record

---

## ADR-001: SQLite and Standard SQL as Storage Foundation

- **Status:** Accepted
- **Context:** Distributed data synchronization can be tackled at the file level (Git), the document level (JSON/CouchDB), or the relational level (SQLite/Postgres).
- **Decision:** Target embedded SQLite databases using standard SQL.
- **Rationale:** SQLite is ubiquitous on edge and mobile devices. Rather than inventing a custom storage engine, developers should retain existing SQLite tools and schemas.
- **Consequences:** Limits v1 scope to single-file relational replicas; non-relational or multi-node server clusters are excluded.

---

## ADR-002: Decoupling Convergence Mechanics from Semantic Resolution

- **Status:** Accepted
- **Context:** Generic CRDTs enforce state convergence but lack domain awareness, often causing silent data loss on relational attributes.
- **Decision:** Separate synchronization into two layers:
  1. **Causality & Convergence Layer:** HLC logical timestamps and change logs establish event ordering.
  2. **Semantic Resolution Layer:** Declarative schema policies (`SUM`, `AVG`, `APPEND`, `REJECT`) decide how divergent values are merged.
- **Rationale:** Allows domain-independent policy execution while preserving convergence guarantees under specified assumptions.

---

## ADR-003: Pre-Runtime Static Type Validation

- **Status:** Accepted
- **Context:** Misconfigured policies (e.g. arithmetic `AVG` assigned to a `TEXT` column) can lead to runtime crashes or silent data corruption during sync.
- **Decision:** Enforce fail-fast static validation via `PolicyValidator`. Any incompatible assignment is rejected with `HTTP 422 Unprocessable Entity` before synchronization is permitted.
- **Rationale:** Upholds Rule 3 of `agent.md`.

---

## ADR-004: Safe Default for Unresolvable Conflicts (`REJECT`)

- **Status:** Accepted
- **Context:** When automated reconciliation cannot be mathematically or safely justified (e.g., conflicting biometric data or primary keys), automated overwrite risks data corruption.
- **Decision:** Default to `REJECT` (status = `flagged`). The conflicting state is persisted in `MergeManager` and neither replica is mutated until manual user review.
- **Rationale:** Safety over aggressive automation.

---

## ADR-005: Multi-Table Foreign Key Integrity via Orphan Quarantine (Phase 5)

- **Status:** Accepted for Phase 5 Implementation
- **Context:** When a parent record is deleted on Replica A while a child record is inserted/updated on Replica B, applying child changes directly violates SQLite foreign key constraints.
- **Decision:** Route orphaned child rows into a dedicated `_ss_quarantine` table with audit metadata. Do NOT automatically resurrect parent records as the default.
- **Rationale:** Automatic resurrection can violate application invariants (e.g., resurrecting a cancelled account). Quarantine preserves data safely while keeping the primary database referentially intact.

---

## ADR-006: Bounded Additive Operations (`BOUNDED_SUM`) (Phase 3)

- **Status:** Accepted for Phase 3 Implementation
- **Context:** Unbounded additive deltas in inventory or financial accounts risk underflow (e.g., stock dropping below zero).
- **Decision:** Introduce `BOUNDED_SUM` policy with explicit boundary checks. If concurrent deltas breach the boundary, flag the conflict for review rather than writing a negative balance.
- **Rationale:** Prevents inventory corruption without requiring full two-phase commit.

---

## ADR-007: Causal Stability Checkpoint for Log Pruning (Phase 6)

- **Status:** Accepted for Phase 6 Implementation
- **Context:** `_ss_change_log` grows monotonically over time. Pruning too early breaks replication for lagging replicas.
- **Decision:** Prune changes only when their HLC timestamp is strictly less than the minimum acknowledged timestamp across all enrolled replicas ($T < \min_{r} T_{\text{ack}}(r)$).
- **Rationale:** Guarantees that no replica is permanently desynchronized by premature log truncation.
