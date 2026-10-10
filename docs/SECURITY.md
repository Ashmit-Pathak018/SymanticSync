# SemanticSync — Security

**Version:** 1.0

---

## Scope

SemanticSync is a **local-only developer tool**. It is not a multi-tenant application, does not expose a public API, and does not transmit data over any network. The security posture reflects this: the primary threats are data integrity and developer safety, not external attacks.

---

## SQL Injection Prevention

**All SQL statements use parameterized queries.**

```python
# ✅ CORRECT — parameterized
conn.execute(
    'UPDATE "products" SET "quantity" = ? WHERE id = ?',
    (resolved_value, row_id)
)

# ❌ NEVER — string interpolation
conn.execute(f'UPDATE products SET quantity = {value} WHERE id = {id}')
```

This rule applies across:
- `ConflictDetector.detect()` — all row reads
- `SemanticResolver` write-back — all resolved value writes
- `CRDTSyncEngine.apply_change()` — all change log inserts
- `routes_query.py` — user-supplied SQL

### Table and Column Name Handling

Table and column names cannot be parameterized in SQLite — they are identifiers, not values. SemanticSync addresses this by:
1. Reading all table/column names from `PRAGMA table_info()` (source of truth)
2. Only using names from that allowlist in any generated SQL
3. Quoting all identifiers: `f'"{ table_name}"'` (double-quoted SQLite identifiers)

---

## Local-Only Operation

SemanticSync has **no network transport layer**:
- No remote database connections
- No WebSockets or streaming
- No outbound HTTP calls
- No authentication tokens or sessions

The API server binds to `127.0.0.1:8000` by default. Never expose it on `0.0.0.0` in production without adding authentication middleware.

---

## Data Sensitivity

SemanticSync is designed to work with potentially sensitive datasets (e.g., the `health` workload contains simulated patient data). Key considerations:

1. **No data leaves the machine** — all processing is local
2. **No logging of row values** — the API does not log field values in access logs
3. **`data/*.db` files should be excluded from version control** — the `.gitignore` excludes `*.db` and `data/*` (with `data/.gitkeep` to preserve the directory)
4. **No PII in `data/registry.json`** — the registry stores only paths, IDs, and policy assignments; not row data

---

## File Access

The engine reads user-supplied SQLite files by path. Validate that:
- The file exists and is readable before opening (`FileNotFoundError` check in `SchemaInspector`)
- The file is a valid SQLite database (first 16 bytes magic number check via `sqlite3.connect`)
- The `data/` directory is writable for replica creation

---

## Parameterized SQL Enforcement (Rule from `agent.md`)

This is Rule 8 in the collaboration contract — **non-negotiable**:

> "All SQL interactions with SQLite databases must use parameterized queries. No f-strings, no `.format()`, no string concatenation for SQL values. Ever."

Any code review that sees raw string SQL with values must be rejected.

---

## Known Security Non-Issues (by design)

| Concern | Status |
|---|---|
| XSS attacks | Frontend only connects to local API; no user-generated HTML |
| CSRF | No cookies; no session; local only |
| Remote code execution | No eval(); no shell commands; no subprocess |
| Dependency vulnerabilities | Minimize deps; run `pip audit` and `npm audit` regularly |
| Secret leaks | No credentials in codebase; `.env` not used |
