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

- **Status:** Implemented for the verified Phase 3 scope; see traceability and limitations for evidence boundaries.
- **Context:** Unbounded additive deltas in inventory or financial accounts risk underflow (e.g., stock dropping below zero).
- **Decision:** `BOUNDED_SUM[min=...,max=...]` enforces explicit inclusive bounds on tracked signed deltas. If a combined candidate breaches either bound, flag it and keep the received operation pending; never clamp or write the out-of-bound value.
- **Rationale:** Prevents tracked operations from materializing an out-of-bound value. Tests cover selected N=3/5 mesh schedules only; they do not establish general convergence, and direct SQL bypasses tracked validation.

---

## ADR-007: Causal Stability Checkpoint for Log Pruning (Phase 6)

- **Status:** The design decision remains recorded; Phase 6 acceptance/sign-off is pending current verification. RESOLVE-tail recovery remains manual-review only.
- **Context:** `_ss_change_log` grows monotonically over time. Pruning too early breaks replication for lagging replicas.
- **Decision:** In the production `/sync/compact` path, exact stable IDs with matching payload hashes across every currently enrolled replica and a strict HLC cutoff are necessary eligibility evidence, not sufficient authorization. Pruning also requires a committed, validated manifest and payload archive; exact member/snapshot binding; verified snapshot identity, schema, data, and operation frontier; valid live tails and replica history; durable ACK reconciliation; and per-operation uniqueness and dependency closure. Missing ACKs or unresolved dependencies retain the log entry. HLC alone never proves delivery. The low-level compaction helper trusts its caller-supplied IDs and cutoff; the production route supplies these only after checkpoint validation.
- **Rationale:** The exact-ID intersection proves recorded receipt while the scalar HLC horizon only limits which acknowledged records are considered. Per-replica receipt and deletion are atomic; a committed partial checkpoint can be retried. New replicas use a current enrolled materialized replica, while returning offline tails are preserved for manual review. The shared ancestor is unchanged. Coordination remains single-process; power-loss durability and arbitrary offline-history recovery are not certified.
