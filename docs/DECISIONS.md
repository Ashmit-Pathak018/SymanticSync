# SemanticSync — Architecture Decision Records (ADRs)

**Version:** 1.0

---

## ADR-001: SQLite as the Conflict Domain

**Status:** Accepted  
**Date:** September 2026

### Context
The conflict resolution problem exists in any distributed database. We needed to choose a concrete target for v1.

### Decision
Target **SQLite** exclusively in v1.

### Rationale
- SQLite is the world's most widely deployed database — billions of devices
- SQLite has a strong and stable PRAGMA introspection API (`table_info`, `sqlite_master`)
- Local-first applications (Obsidian, Linear, Notion desktop, etc.) are predominantly SQLite-backed
- Standard Python `sqlite3` module requires zero additional dependencies
- SQLite's type affinity system is well-defined and maps cleanly to our 5 normalized types

### Consequences
- Incompatible with PostgreSQL, MySQL, or cloud databases in v1
- Row-level addressing only (no JSONB or nested document support)

---

## ADR-002: Semantic Policy Layer Above CRDT Convergence

**Status:** Accepted  
**Date:** September 2026

### Context
Generic CRDT approaches (LWW registers, G-counters, etc.) ensure convergence but not semantic correctness. We could have implemented either:
1. Extend CRDT data types with semantic behavior built-in
2. Add a separate semantic resolution layer that runs on top of generic CRDTs

### Decision
**Option 2: Separate semantic policy layer.** CRDTSyncEngine handles convergence; SemanticResolver handles correctness.

### Rationale
- **Decoupling:** CRDTs can evolve independently of business semantics
- **Domain agnosticism:** The engine layer must be free of domain logic
- **Testability:** Each layer can be unit-tested independently
- **Flexibility:** Policies can be changed at runtime; the CRDT mechanism does not change

### Consequences
- Slightly more complex architecture
- Must ensure the resolution layer is called after CRDT sync, not instead of it

---

## ADR-003: FastAPI over Flask/Django

**Status:** Accepted  
**Date:** September 2026

### Context
Python web framework selection for the REST API.

### Decision
**FastAPI** with Pydantic v2 models.

### Rationale
- Automatic OpenAPI/Swagger documentation out of the box
- Pydantic v2 provides fast, type-safe request validation
- Async-ready (`async def`) for future non-blocking replica I/O
- Much faster than Django for this lightweight stateless API use case
- Better developer ergonomics for a research project than Flask (no hand-written validation)

---

## ADR-004: In-Memory + JSON Persistence (No ORM)

**Status:** Accepted  
**Date:** September 2026

### Context
We needed to persist API-level state (registered databases, policies, conflicts). Options:
1. SQLite as a metadata store (with SQLAlchemy or raw SQL)
2. In-memory dict + JSON file persistence

### Decision
**Option 2: `AppState` class with JSON persistence** at `data/registry.json`.

### Rationale
- Zero additional dependencies (no SQLAlchemy, no alembic)
- No risk of interfering with the target SQLite databases under test
- Simple to reason about for a research project
- Avoids recursive meta-problem: using SQLite to manage SQLite sync metadata
- JSON is human-readable and debuggable

### Consequences
- Not suitable for concurrent multi-process access
- Not suitable for >10k conflicts in memory (v1 scope is fine)
- `write_text()` used instead of `os.replace()` to avoid Windows `PermissionError`

---

## ADR-005: Hybrid Logical Clock over Lamport Clocks

**Status:** Accepted  
**Date:** September 2026

### Context
Replica change ordering requires a causally consistent clock. Options:
1. Lamport Clocks (pure logical)
2. Vector Clocks (per-node)
3. Hybrid Logical Clocks (HLC)

### Decision
**Hybrid Logical Clocks (HLC).**

### Rationale
- HLCs encode both physical time and logical ordering
- They remain close to wall-clock time (useful for debugging timestamps)
- They are compact — a (pt, l) tuple per node
- Standard choice in modern distributed databases (CockroachDB, YugabyteDB)
- LWW policy benefits from physical-time proximity for human comprehension

### Consequences
- Requires all nodes to have roughly synchronized system clocks (acceptable for local-first)

---

## ADR-006: Parameterized SQL Only

**Status:** Non-negotiable  
**Date:** September 2026

### Context
The engine must write SQL to user-supplied SQLite databases.

### Decision
**All SQL uses parameterized queries (`?` placeholders).** String interpolation in SQL is strictly prohibited.

### Rationale
- SQL injection prevention (even in local tools, best practices must be followed)
- Consistent with Rule 5 in `agent.md`
- SQLite's `check_same_thread=False` is used for multi-threaded FastAPI context

### Consequences
- Slightly more verbose code
- Table and column names are still interpolated as identifiers (sanitized via allowlist from schema)

---

## ADR-007: Design Token System for Frontend

**Status:** Accepted  
**Date:** October 2026

### Context
The SemanticSync Studio frontend needs a cohesive visual language for conflict states, resolutions, and policy types.

### Decision
**Fixed design token palette** (see `docs/DESIGN_SYSTEM.md`). No arbitrary color values in component code.

### Rationale
- Visual consistency across all views
- Tokens map semantically to application states (Danger = conflict, Success = resolved)
- Shared language between design and code via Tailwind `extend.colors`

### Consequences
- Frontend contributors must use token names, not hex values directly
