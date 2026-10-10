# SemanticSync — Coding Standards

**Version:** 1.0

---

## Python Standards

### Type Annotations
All functions must have complete type annotations:
```python
# ✅ Correct
def resolve(self, policy: PolicyType, base_value: Any, value_a: Any, value_b: Any) -> ResolutionResult:

# ❌ Missing annotations
def resolve(self, policy, base_value, value_a, value_b):
```

### Docstrings
Public classes and methods must have docstrings:
```python
class SchemaInspector:
    """Introspects SQLite database schemas via PRAGMA commands.
    
    Reads column metadata, data types, and constraints without
    modifying the target database.
    """
    
    def inspect_table(self, table_name: str) -> list[ColumnInfo]:
        """Return all columns for the given table.
        
        Args:
            table_name: Name of the SQLite table to inspect.
            
        Returns:
            List of ColumnInfo dataclasses, one per column.
            
        Raises:
            FileNotFoundError: If the database file does not exist.
        """
```

### Dataclasses over Dicts
Use `@dataclass` for structured data, not plain dicts:
```python
# ✅
@dataclass
class ResolutionResult:
    status: str
    resolved_value: Any
    policy: PolicyType
    explanation: str
    is_deterministic: bool

# ❌
result = {
    "status": "resolved",
    "resolved_value": 135,
    ...
}
```

### Import Order
Standard library → third-party → local (follow isort rules):
```python
# stdlib
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Optional

# third-party
from pydantic import BaseModel
from fastapi import HTTPException

# local
from backend.engine.policy_registry import PolicyType
from backend.engine.schema_inspector import SchemaInspector
```

---

## Engine Layer Rules (from `agent.md`)

### Rule: No Domain Logic in Engine
The `backend/engine/` directory must never contain domain-specific terminology:

```python
# ❌ NEVER in engine layer
if column == "blood_type":
    return "REJECT"

if table == "inventory" and column == "quantity":
    return SUM(...)

# ✅ Engine operates on generic types and registered policies
policy = self.registry.get_policy(policy_name)
return self._apply(policy, base_value, value_a, value_b)
```

### Rule: Parameterized SQL Only
```python
# ✅ ALWAYS
conn.execute('UPDATE "products" SET "quantity" = ? WHERE id = ?', (value, row_id))

# ❌ NEVER
conn.execute(f'UPDATE products SET quantity = {value} WHERE id = {row_id}')
```

### Rule: Determinism
All resolution functions must be pure and deterministic:
- No `random`
- No `time.time()` inside resolution functions (timestamps are inputs, not reads)
- No network calls
- No side effects (reading state is OK; writing is not)

---

## API Layer Rules

### HTTP Status Codes
| Situation | Code |
|---|---|
| Successful creation | `201 Created` |
| Successful read/update | `200 OK` |
| Not found | `404 Not Found` |
| Validation/type error | `422 Unprocessable Entity` |
| SQL error | `400 Bad Request` |
| Server error | `500 Internal Server Error` |

### Response Consistency
All list endpoints return a list (empty list `[]`, never `null`):
```python
# ✅
return []

# ❌
return None
```

---

## Frontend Standards

### No Inline Styles
```jsx
// ✅
<div className="bg-workspace border border-border rounded-lg p-4">

// ❌
<div style={{ backgroundColor: '#F4F6FA', border: '1px solid #D8DEEA' }}>
```

### No Raw Hex Values in Code
```jsx
// ✅ — use Tailwind token name
<span className="text-danger">Flagged</span>

// ❌ — raw hex in className
<span className="text-[#D94B5B]">Flagged</span>
```

### Component Naming
- Components: `PascalCase` — `ConflictCard`, `PolicySelector`
- Hooks: `camelCase` with `use` prefix — `useConflicts`, `usePolicies`
- Utilities: `camelCase` — `formatTimestamp`, `normalizeType`
- Files: match component name — `ConflictCard.jsx`, `usePolicies.js`

### No Hardcoded API URL
```js
// ✅
import { api } from '../services/api';
const data = await api.getDatabases();

// ❌
const data = await fetch('http://127.0.0.1:8000/api/v1/databases');
```

---

## Git Commit Format

Follow Conventional Commits:
```
feat: add APPEND policy support for TEXT columns
fix: resolve Windows PermissionError in AppState.save()
docs: add CONFLICT_MODEL.md
test: add commutativity tests for SUM resolver
refactor: extract type normalization into SchemaInspector
chore: update requirements.txt with exact versions
```

---

## Testing Standards

- All tests use `tmp_path` fixture for file-based tests (no hardcoded paths)
- No `os.getcwd()` or relative path assumptions in tests
- Each test is independent — tests must not share state
- No `time.sleep()` in tests
