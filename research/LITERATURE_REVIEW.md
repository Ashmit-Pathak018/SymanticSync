# SemanticSync — Literature Review

**Version:** 1.0  
**Field:** Distributed Systems, Local-First Software, Conflict-Free Replicated Data Types

---

## 1. Foundational CRDT Theory

### Shapiro et al. (2011) — Conflict-Free Replicated Data Types
- *Citation:* Shapiro, M., Preguiça, N., Baquero, C., & Zawirski, M. (2011). *Conflict-free replicated data types*. SSS 2011.
- *Relevance:* Established the formal mathematical foundations for state-based (CvRDT) and operation-based (CmRDT) convergence. Proved that monotonic semi-lattices ensure Strong Eventual Consistency without consensus rounds.
- *Limitation relative to SemanticSync:* Standard CvRDT registers (e.g., LWW-Register, Multi-Value Register) either discard concurrent values or delegate conflict sets to the application layer without relational schema awareness.

---

## 2. Local-First Software & Edge Databases

### Kleppmann et al. (2019) — Local-First Software: You Own Your Data, in spite of the Cloud
- *Citation:* Kleppmann, M., Wiggins, A., van Hardenberg, M. A., & McGranaghan, M. (2019). *Local-first software: you own your data, in spite of the cloud*. Onward! 2019.
- *Relevance:* Outlined seven ideals of local-first computing, prioritizing client-side storage, offline capability, cross-device synchronization, and conflict resolution.
- *Connection to SemanticSync:* SemanticSync provides a practical relational realization of local-first ideals directly on developer-standard SQLite engines.

### Kulkarni et al. (2014) — Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases
- *Citation:* Kulkarni, S., Dachiraju, M., & Liu, S. (2014). *Logical physical clocks and consistent snapshots in globally distributed databases*.
- *Relevance:* Formulated the Hybrid Logical Clock (HLC) algorithm, bounding logical tick advancement to physical wall-clock drift while providing causal ordering and strict monotonicity.
- *Usage in SemanticSync:* Utilized within `backend/engine/crdt_sync.py` to deterministically order concurrent writes across replicas.

---

## 3. Relational CRDTs and Database Merging

### CR-SQLite and VLCN
- *Relevance:* CR-SQLite embeds fractional index and run-length CRDT algorithms as SQLite loadable C extensions. It tracks column-level mutations using change logs (`crsql_changes`).
- *Contrast:* CR-SQLite operates primarily as a Last-Write-Wins column-level engine or delta-state tracker. It does not provide extensible declarative semantic policies (such as delta `SUM`, arithmetic `AVG`, or deterministic delimiter `APPEND`) configured at the schema abstraction level.

### Operational Transformation (OT) vs. CRDTs in Collaborative Contexts
- *Relevance:* While OT (Ellis & Gibbs, 1989) successfully powers character-by-character text collaboration (e.g., Google Docs), it requires centralized transformation servers. CRDTs enable decentralized peer exchange.
- *SemanticSync's position:* Leverages declarative policies above the relational schema, bringing CRDT safety to structured business rows.

---

## 4. Gaps in Existing Research

| Approach | Convergence Guarantee | Semantic Awareness | Type-Level Validation | Pure SQLite Native |
|---|---|---|---|---|
| Git / 3-Way Text Diff | ❌ (Frequent merge conflicts) | ❌ Textual only | ❌ None | ❌ |
| Traditional LWW CRDT | ✅ (SEC) | ❌ Last timestamp wins | ❌ Blind register | ⚠️ (Requires custom wrappers) |
| Multi-Value Register (MVR) | ✅ (SEC) | ⚠️ Retains all, defers | ❌ No resolution | ❌ |
| **SemanticSync** | **✅ (SEC via HLC + Semantics)** | **✅ Declarative Policies** | **✅ Pre-sync Validator** | **✅ Pure SQLite + Python** |
