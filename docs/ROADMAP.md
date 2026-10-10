# SemanticSync — Roadmap

**Version:** 1.0

---

## Release Track

```
v0.1.0  ✅  Backend core + REST API (September 2026)
v0.2.0  🔄  Documentation suite (October 2026)
v0.3.0  📋  SemanticSync Studio frontend
v0.4.0  📋  Research evaluation results
v1.0.0  📋  First stable release + paper submission
```

---

## Short-Term (v0.3.0 — Studio Frontend)

**Target:** November 2026

- [ ] React 18 + Vite + Tailwind scaffold
- [ ] Sidebar navigation shell
- [ ] Dashboard view: workspace cards + conflict badges
- [ ] Schema & Policy Designer: inline assignment + validation
- [ ] SQL Console: CodeMirror 6 + replica selector + results table
- [ ] Conflict Manager: list, filter, expand, manual resolve
- [ ] Sync Control Panel: run sync + generate-conflict
- [ ] Benchmark view: SCR bar chart + metrics table
- [ ] One-click seed button for all workloads

---

## Medium-Term (v0.4.0 — Research Evaluation)

**Target:** December 2026

- [ ] Full benchmark suite across all 3 workloads (Inventory, Notes, Health)
- [ ] 100-trial statistical stability experiment
- [ ] Formal SCR calculation and recording
- [ ] Resolution overhead profiling (ms/conflict)
- [ ] Results documented in `research/RESULTS_PROTOCOL.md`

---

## Long-Term (v1.0.0+ — Beyond v1)

### Multi-Table Sync
- Conflict detection across multiple related tables in a single sync run
- JOIN-aware conflict scope

### Multi-Replica Pairwise Sync
- Extend sync to N replicas (not just pair-wise A vs B)
- Topology-aware sync ordering (star, mesh, ring)

### Network Transport Layer
- Peer-to-peer change propagation over LAN
- Change log exchange via HTTP or WebSockets
- Delta sync (only changes since last checkpoint)

### Policy Inheritance
- Table-level default policies (fallback for unassigned columns)
- Schema-level wildcard policies

### INSERT Conflict Handling
- Detect and resolve conflicts from concurrent row insertions with same PK
- Configurable: reject, uuid-rename, or merge-by-timestamp

### Binary/BLOB Policy Support
- Hash-based comparison for BLOB fields
- `LAST_WRITE_WINS_BLOB` policy using byte-level checksums

### Plugin Policy API
- Developer-defined custom policies via Python plugin interface
- Policy lifecycle hooks (pre-resolve, post-resolve)

### Studio UI Enhancements
- Dark mode
- Export benchmark results as CSV/PDF
- Shareable conflict review links (local URL deep links)
- Policy assignment template import/export (JSON)

---

## Explicitly Out of Scope (v1)

- Cloud synchronization or hosted backend
- PostgreSQL, MySQL, MongoDB, or any non-SQLite database
- Authentication or multi-user access control
- Mobile client (iOS/Android)
- Real-time collaborative editing (CRDTs operating on characters/keystrokes)
