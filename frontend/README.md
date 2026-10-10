# SemanticSync Studio 🔄

> **Developer workspace UI for local-first relational databases with schema-level semantic merge policies.**

SemanticSync Studio is the developer interface for inspecting SQLite schemas, configuring attribute-level merge policies (`SUM`, `AVG`, `APPEND`, `LWW`, `REJECT`, `MIN`, `MAX`), observing live three-way CRDT synchronization across offline replicas, and running research benchmark suites.

---

## 🛠️ Tech Stack
- **Framework:** React 19
- **Build Tool:** Vite 8
- **Styling:** Tailwind CSS 3
- **Icons:** Lucide React
- **Routing:** React Router DOM 7
- **API Client:** Native Fetch with Vite reverse-proxy to FastAPI (`/api/v1`)

---

## 🚀 Development

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Dev Server
```bash
npm run dev
```
Studio will be available at `http://localhost:5173`. API requests to `/api` are automatically proxied to the backend at `http://127.0.0.1:8000`.

### 3. Production Build
```bash
npm run build
```
Production assets are generated in `dist/`.
