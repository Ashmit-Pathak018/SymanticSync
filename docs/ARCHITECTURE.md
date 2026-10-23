# SemanticSync — System Architecture

**Version:** 2.0 (Reconciled)  
**Status:** Approved Technical Architecture

---

## 1. System Topology

SemanticSync is designed as a modular middleware layer operating between application SQL execution and physical SQLite storage:

```
┌────────────────────────────────────────────────────────────────────────┐
│                 SemanticSync Studio (Frontend)                         │
│  React 18 + Vite + Tailwind CSS                                        │
│  Dashboard │ Schema Editor │ Conflicts │ Sync Hub │ SQL Console │ Analytics │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST /api/v1
┌───────────────────────────────────▼────────────────────────────────────┐
│              SemanticSync API Server (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │ Database API │  │  Policy API  │  │  Sync & Conflict Engine API  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┬───────────────┘  │
│         └─────────────────┴─────────────────────────┘                  │
│                           │                                            │
│              ┌────────────▼────────────┐                               │
│              │       AppState          │                               │
│              │   (In-Memory + JSON)    │                               │
│              └────────────┬────────────┘                               │
│                           │                                            │
│  ┌────────────────────────▼──────────────────────────────────────────┐ │
│  │                     Semantic Engine Core                          │ │
│  │  ┌──────────────────┐  ┌───────────────────────────────────────┐  │ │
│  │  │ Schema Inspector │  │   Policy Registry & Type Validator    │  │ │
│  │  └──────────────────┘  └───────────────────────────────────────┘  │ │
│  │  ┌──────────────────┐  ┌───────────────────────────────────────┐  │ │
│  │  │Conflict Detector │  │          Semantic Resolver            │  │ │
│  │  └──────────────────┘  └───────────────────────────────────────┘  │ │
│  │  ┌──────────────────┐  ┌───────────────────────────────────────┐  │ │
│  │  │  Merge Manager   │  │   CRDTSyncEngine + HLC + Change Log   │  │ │
│  │  └──────────────────┘  └───────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Parameterized SQL
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
     Replica A                 Replica B                 Replica C
    (SQLite .db)              (SQLite .db)              (SQLite .db)
```

---

## 2. Component Responsibilities

### 1. Schema Inspector (`backend/engine/schema_inspector.py`)
- Discovers user tables and primary keys using SQLite `PRAGMA table_info`.
- Normalizes declared SQLite affinities into 5 canonical types: `INTEGER`, `REAL`, `TEXT`, `BLOB`, `NUMERIC`.

### 2. Policy Registry & Validator (`backend/engine/policy_registry.py`, `policy_validator.py`)
- Manages policy definitions: `SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`.
- Enforces static type compatibility. Returns `HTTP 422 Unprocessable Entity` with `TYPE_INCOMPATIBLE` error code for invalid pairings.

### 3. Conflict Detector (`backend/engine/conflict_detector.py`)
- Performs 3-way differential inspection comparing ancestor base snapshot against replica states.
- Identifies true concurrent divergences: $S_A \neq S_{\text{base}} \land S_B \neq S_{\text{base}} \land S_A \neq S_B$.

### 4. Semantic Resolver (`backend/engine/semantic_resolver.py`)
- Executes deterministic policy reconciliation logic.
- Returns `ResolutionResult(status, resolved_value, policy, explanation)`.
- Guarantees commutativity for symmetric policies ($A \sqcup B = B \sqcup A$).

### 5. CRDT Sync Engine & HLC (`backend/engine/crdt_sync.py`)
- Manages replica forking and tracked writes.
- Ticks Hybrid Logical Clock on every mutation.
- Records operations into `_ss_change_log`.
- Executes the detect $\to$ validate $\to$ resolve $\to$ write-back pipeline.

### 6. Merge Manager (`backend/engine/merge_manager.py`)
- Persists detected conflicts and resolution histories.
- Manages unmerged `flagged` conflict records for manual user review.

### 7. Foreign-Key Enforcement and Quarantine (`fk_quarantine.py`)
- Tracked mutation, receive, paired-resolution, and quarantine-recovery connections enable SQLite foreign keys before opening write transactions.
- Supported parent-delete paths move declared dependent rows recursively into `_ss_quarantine` in the same transaction, then verify `PRAGMA foreign_key_check` before commit.
- Parent-key updates follow the schema's declared SQLite `ON UPDATE` action; they are not quarantined. Unsupported target schemas (including composite parent keys and some `WITHOUT ROWID` dependent schemas) are rejected without committing a partial delete.
- SQL-console connections also enable foreign keys, but their writes do not enter the tracked operation log or quarantine workflow and bypass the process mutation lock. External SQLite clients can bypass the process lock and may disable foreign keys per connection.
