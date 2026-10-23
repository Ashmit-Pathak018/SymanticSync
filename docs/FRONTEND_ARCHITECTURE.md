# SemanticSync — Frontend Architecture

**Version:** 1.0

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | React | 18+ |
| Build Tool | Vite | 5+ |
| Styling | Tailwind CSS | 3+ |
| HTTP Client | Axios or Fetch API | — |
| Icons | Lucide React | latest |
| Routing | React Router DOM | 6+ |
| State Management | React Context + `useState`/`useReducer` | — |
| Code Editor | CodeMirror 6 | latest |

---

## Project Structure

```
frontend/
├── public/
│   └── logo.svg
├── src/
│   ├── main.jsx              ← React app entry point
│   ├── App.jsx               ← Router setup
│   ├── services/
│   │   └── api.js            ← All HTTP calls to backend
│   ├── context/
│   │   └── AppContext.jsx    ← Global state (selected DB, etc.)
│   ├── components/
│   │   ├── ui/               ← Generic: Button, Badge, Card, Modal
│   │   ├── layout/           ← Sidebar, TopBar, PageShell
│   │   ├── schema/           ← SchemaTable, PolicySelector, ColumnRow
│   │   ├── conflicts/        ← ConflictList, ConflictCard, ResolvePanel
│   │   ├── sql/              ← SqlEditor, ResultsTable
│   │   ├── sync/             ← SyncStatus, SyncForm, SyncResult
│   │   └── benchmark/        ← BenchmarkForm, MetricsDisplay, SCRBar
│   ├── views/
│   │   ├── Dashboard.jsx
│   │   ├── DatabaseList.jsx
│   │   ├── SchemaDesigner.jsx
│   │   ├── SqlConsole.jsx
│   │   ├── ConflictManager.jsx
│   │   ├── SyncControl.jsx
│   │   ├── Benchmark.jsx
│   │   └── ReplicaManager.jsx
│   └── utils/
│       ├── formatters.js     ← Date/value formatting helpers
│       └── typeColors.js     ← Normalized type → badge color map
├── index.html
├── vite.config.js
├── tailwind.config.js
└── package.json
```

---

## API Service Layer (`services/api.js`)

All backend calls are centralized here. No `fetch`/`axios` calls in components.

```js
const BASE = 'http://127.0.0.1:8000/api/v1';

export const api = {
  // Databases
  getDatabases: ()            => fetch(`${BASE}/databases`).then(r => r.json()),
  registerDatabase: (body)    => fetch(`${BASE}/databases`, { method: 'POST', json: body }),
  getDatabaseSchema: (dbId)   => fetch(`${BASE}/databases/${dbId}/schema`).then(r => r.json()),
  getReplicas: (dbId)         => fetch(`${BASE}/databases/${dbId}/replicas`).then(r => r.json()),
  createReplica: (dbId, body) => fetch(`${BASE}/databases/${dbId}/replicas`, { method: 'POST', json: body }),

  // Policies
  getPolicies: (dbId)        => fetch(`${BASE}/databases/${dbId}/policies`).then(r => r.json()),
  setPolicies: (dbId, body)  => fetch(`${BASE}/databases/${dbId}/policies`, { method: 'PUT', json: body }),
  getPolicyRegistry: ()      => fetch(`${BASE}/policies/registry`).then(r => r.json()),
  validatePolicy: (body)     => fetch(`${BASE}/validate-policy`, { method: 'POST', json: body }),

  // Conflicts
  detectConflicts: (body)    => fetch(`${BASE}/conflicts/detect`, { method: 'POST', json: body }),
  resolveConflict: (body)    => fetch(`${BASE}/conflicts/resolve`, { method: 'POST', json: body }),
  getConflicts: (params)     => fetch(`${BASE}/conflicts?${params}`).then(r => r.json()),

  // Sync
  getSyncStatus: ()          => fetch(`${BASE}/sync/status`).then(r => r.json()),
  runSync: (body)            => fetch(`${BASE}/sync/run`, { method: 'POST', json: body }),
  generateConflict: (body)   => fetch(`${BASE}/sync/generate-conflict`, { method: 'POST', json: body }),

  // Query
  executeQuery: (body)       => fetch(`${BASE}/query`, { method: 'POST', json: body }),

  // Benchmark
  // Returns only illustrative_unvalidated status; domain output is not empirical telemetry.
  runBenchmark: (workload)   => fetch(`${BASE}/benchmark/run`, { method: 'POST', json: { workload } }),
  getMetrics: ()             => fetch(`${BASE}/metrics`).then(r => r.json()),

  // Seed
  seed: (workload)           => fetch(`${BASE}/seed`, { method: 'POST', json: { workload } }),
};
```

---

## Routing Structure

```jsx
// App.jsx
<Routes>
  <Route path="/" element={<Dashboard />} />
  <Route path="/databases" element={<DatabaseList />} />
  <Route path="/workspace/:dbId/schema" element={<SchemaDesigner />} />
  <Route path="/workspace/:dbId/sql" element={<SqlConsole />} />
  <Route path="/workspace/:dbId/replicas" element={<ReplicaManager />} />
  <Route path="/conflicts" element={<ConflictManager />} />
  <Route path="/sync" element={<SyncControl />} />
  <Route path="/benchmark" element={<Benchmark />} />
</Routes>
```

---

## State Management

Light global state via React Context:

```js
// AppContext.jsx
const AppContext = createContext({
  selectedDbId: null,
  selectedReplicaId: null,
  policyRegistry: [],
  setSelectedDbId: () => {},
});
```

Per-view state lives in local `useState`. No Redux or Zustand needed for v1 scope.

---

## Key Component Specs

### `PolicySelector`
- Dropdown rendering all 7 policies
- On change: immediate `POST /api/v1/validate-policy`
- Renders ✅ Valid or ❌ TYPE_INCOMPATIBLE inline
- Disables Save button if any column is invalid

### `ConflictCard`
- Shows: table, column, row_id, policy, base/a/b values, resolved value
- Status badge: `resolved` (success), `pending` (warning), `flagged` (danger)
- Expandable accordion for full details + resolve actions

### `SqlEditor`
- CodeMirror 6 with SQLite syntax highlighting
- Ctrl+Enter / Cmd+Enter to execute
- Replica selector dropdown above editor

### `SCRBar`
- Horizontal progress bar for Semantic Correctness Rate
- Baseline (LWW) bar in `warning` color, SemanticSync bar in `primary` color
- Numeric percentage labels

---

## Build and Dev

```bash
# Install
cd frontend
npm install

# Dev server (with API proxy to :8000)
npm run dev

# Production build
npm run build
```

Vite proxy config:
```js
// vite.config.js
export default {
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  }
}
```
