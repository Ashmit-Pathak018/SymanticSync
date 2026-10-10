# SemanticSync — UX Specification

**Version:** 1.0

---

## Design Philosophy

SemanticSync Studio is a **developer tool**, not a consumer app. The UX prioritizes:
- **Density over whitespace:** Developers expect to see data, not decoration
- **Immediacy:** All actions produce visible feedback within the same view
- **Progressive disclosure:** Advanced conflict details are collapsed by default
- **Semantic color coding:** Colors map to application states, not decorative choices

---

## Navigation Structure

```
Sidebar (persistent, 48px wide icon strip on left)
├── 🏠 Dashboard
├── 🗄️  Workspace / Database List
│   └── [database]
│       ├── Schema & Policy Designer
│       ├── SQL Console
│       └── Replicas
├── ⚡ Conflict Manager
├── 🔄 Sync Control
├── 📊 Benchmark
└── ⚙️  Settings (future)
```

---

## View 1: Dashboard

**Route:** `/`

**Purpose:** At-a-glance health of all registered workspaces.

**Layout:**
```
┌───────────────────────────────────────────────────────┐
│  SemanticSync Studio                    v1.0  [Status]│
│  ─────────────────────────────────────────────────────│
│  [+] Register Database                                 │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │ Inventory    │  │ Notes        │  │ Healthcare   ││
│  │ 1 table      │  │ 1 table      │  │ 1 table      ││
│  │ 3 replicas   │  │ 3 replicas   │  │ 3 replicas   ││
│  │ 1 conflict⚡ │  │ 0 conflicts  │  │ 2 flagged 🔴 ││
│  │ [Open →]     │  │ [Open →]     │  │ [Open →]     ││
│  └──────────────┘  └──────────────┘  └──────────────┘│
└───────────────────────────────────────────────────────┘
```

**Components:**
- Database cards with conflict badges
- "Register Database" modal
- API connection status indicator (green dot = server up)

---

## View 2: Schema & Policy Designer

**Route:** `/workspace/:dbId/schema`

**Purpose:** Browse schema tables and assign semantic policies column-by-column.

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│  Inventory Workspace → Schema & Policies                  │
│  ──────────────────────────────────────────────────────── │
│  Table: [products ▼]                                       │
│                                                            │
│  Column       Type        Policy          Status          │
│  ────────     ────────    ────────────    ─────────────   │
│  id (PK)      INTEGER     [N/A - PK]      —              │
│  sku          TEXT        [REJECT ▼]      ✅ Valid         │
│  name         TEXT        [LWW    ▼]      ✅ Valid         │
│  quantity     INTEGER     [SUM    ▼]      ✅ Valid         │
│  unit_price   REAL        [AVG    ▼]      ✅ Valid         │
│  description  TEXT        [APPEND ▼]      ✅ Valid         │
│                                                            │
│  [Save All Policies]      [Reset to Default]              │
└──────────────────────────────────────────────────────────┘
```

**Validation UX:**
- Selecting an incompatible policy (e.g. `SUM` on `TEXT`) immediately shows:
  - Red badge: `❌ TYPE_INCOMPATIBLE: SUM is not compatible with TEXT. Use APPEND or LWW.`
- Save button is disabled until all assignments are valid

---

## View 3: SQL Console

**Route:** `/workspace/:dbId/sql`

**Purpose:** Execute SQL queries against any replica or the base database.

See `docs/SQL_CONSOLE.md` for full specification.

---

## View 4: Conflict Manager

**Route:** `/conflicts`

**Purpose:** Inspect, filter, and manually resolve flagged conflicts.

**Layout:**
```
┌───────────────────────────────────────────────────────────┐
│  Conflict Manager              [pending: 2] [flagged: 1]   │
│  ─────────────────────────────────────────────────────────│
│  Filter: [All ▼]  DB: [All ▼]  Table: [All ▼]            │
│                                                            │
│  ID           Table     Column     Status     Policy       │
│  ──────────   ───────   ────────   ────────   ─────────    │
│  a3f9...      products  quantity   resolved   SUM          │
│  b8c1...      products  sku        flagged 🔴 REJECT        │
│  e2d5...      notes     body       pending    APPEND        │
│                                                            │
│  [Expand row → show base/a/b values, resolved value, exp.] │
└───────────────────────────────────────────────────────────┘
```

**Expanded Row:**
```
▼ b8c1... | products.sku | row_id: 1 | FLAGGED
  Base:      SKU-001
  Replica A: SKU-UPDATED
  Replica B: SKU-001
  
  Resolution: [Pick A] [Pick B] [Custom: ___________] [Apply]
```

---

## View 5: Sync Control Panel

**Route:** `/sync`

**Purpose:** Run synchronization, generate test conflicts, view history.

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│  Sync Control                                             │
│  ─────────────────────────────────────────────────────── │
│  Database: [Inventory ▼]   Replica A: [device_a ▼]       │
│                            Replica B: [device_b ▼]       │
│                                                            │
│  [Run Sync]   [Generate Conflict]                         │
│                                                            │
│  Last Sync: Oct 10 2026 18:00:00                          │
│  Result: 3 conflicts | 2 resolved | 1 flagged             │
│  Duration: 12.4ms                                         │
│                                                            │
│  Applied Changes:                                          │
│  ─────────────────────────────────────────────────────── │
│  • products.quantity → 135 (SUM: 100+15+20)               │
│  • notes.body → "..." (APPEND)                            │
└──────────────────────────────────────────────────────────┘
```

---

## View 6: Benchmark

**Route:** `/benchmark`

**Purpose:** Compare Generic LWW baseline vs. SemanticSync across all workloads.

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│  Benchmark Results                                        │
│  Workload: [Inventory ▼]   [Run Benchmark]                │
│  ─────────────────────────────────────────────────────── │
│                                                            │
│  Semantic Correctness Rate (SCR)                          │
│  Generic LWW:    ████░░░░░░  33.3%                        │
│  SemanticSync:   ██████████ 100.0%                        │
│                                                            │
│  Conflicts Evaluated: 3                                    │
│  Correct Outcomes:    3 / 3                               │
│  Resolution Overhead: 0.05ms / conflict                   │
└──────────────────────────────────────────────────────────┘
```

---

## View 7: Replica Manager

**Route:** `/workspace/:dbId/replicas`

**Purpose:** List and create replicas for a database.

---

## Interaction Patterns

| Interaction | Behavior |
|---|---|
| Policy dropdown change | Immediate inline validation (no submit) |
| Save Policies | Full batch PUT + toast notification |
| Run Sync | Full-page loading spinner → result card |
| SQL Execute | Results appear below editor in < 1s |
| Conflict expand | Smooth accordion reveal |
| Pick A / Pick B | Optimistic UI update → confirmed by API |
