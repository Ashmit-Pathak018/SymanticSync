# SemanticSync — Data Models Reference

**Version:** 2.0 (Phase 2 Row-Mutation Model)  
**Status:** Implementation-Ready Specification

---

## 1. Engine Layer Data Models

These are internal Python dataclasses used by the engine layer (`backend/engine/`).

### `ConflictInfo`
```python
@dataclass
class ConflictInfo:
    conflict_id: str             # UUID4 string
    table: str                   # SQLite table name
    row_id: Any                  # Primary key value (int, str, etc.)
    column: str                  # Column name, or '*' for whole-row conflicts
    conflict_type: str = "UPDATE_UPDATE" # "UPDATE_UPDATE" | "INSERT_INSERT" | "UPDATE_DELETE" | "UNIQUE_COLLISION"
    base_value: Any = None       # Common ancestor value or row dict (None for INSERTs)
    replica_a_value: Any = None  # Value or row payload from Replica A
    replica_b_value: Any = None  # Value or row payload from Replica B
    replica_a_id: str = ""       # Replica A logical name
    replica_b_id: str = ""       # Replica B logical name
    replica_a_ts: float = 0.0    # HLC composite timestamp for A's write
    replica_b_ts: float = 0.0    # HLC composite timestamp for B's write
    detected_at: str = ""        # ISO-8601 UTC string
    status: str = "pending"      # "pending" | "resolved" | "flagged"
    resolution_mode: Optional[str] = None # "auto" | "pick_a" | "pick_b" | "custom"
    resolved_value: Optional[Any] = None
    explanation: Optional[str] = None
```

### `ResolutionResult`
```python
@dataclass
class ResolutionResult:
    status: Literal["resolved", "flagged"]
    resolved_value: Any         # Merged value or row payload (None if flagged or deleted)
    policy: Any                 # Policy that produced this result (PolicyType, str, or tombstone policy)
    explanation: str            # Human-readable merge rationale
    is_deterministic: bool = True # Always True for deterministic policies
```

### `ValidationResult`
```python
@dataclass
class ValidationResult:
    valid: bool
    policy: Optional[str | PolicyType]
    error_code: Optional[str]       # "TYPE_INCOMPATIBLE" | "UNKNOWN_POLICY"
    error_message: Optional[str]    # Human-readable explanation
```

### `SyncResult`
```python
@dataclass
class SyncResult:
    total_conflicts: int
    auto_resolved: int
    flagged_for_review: int
    applied_changes: list[dict]     # Each applied change record
    flagged_conflicts: list[str]    # conflict_ids flagged for review
    duration_ms: float
```

### `HLC`
```python
@dataclass
class HLC:
    pt: float       # Physical timestamp (seconds since epoch)
    l: int          # Logical counter
    node_id: str    # Unique node/replica identifier
```

---

## 2. API Layer Data Models (Pydantic v2)

These are used by FastAPI for request validation and response serialization (`backend/api/models.py`).

### `ConflictRecordResponse`
```python
class ConflictRecordResponse(BaseModel):
    conflict_id: str
    db_id: Optional[str] = None
    table: str
    row_id: Any
    column: str
    conflict_type: str = "UPDATE_UPDATE"
    base_value: Optional[Any] = None
    value_a: Optional[Any] = None
    value_b: Optional[Any] = None
    replica_a_id: str
    replica_b_id: str
    replica_a_ts: float
    replica_b_ts: float
    status: str
    detected_at: str
    policy: Optional[str] = None
    resolved_value: Optional[Any] = None
    explanation: Optional[str] = None
```

### `ConflictResolveRequest`
```python
class ConflictResolveRequest(BaseModel):
    conflict_id: str
    resolution_mode: str   # 'auto' | 'pick_a' | 'pick_b' | 'custom'
    custom_value: Optional[Any] = None
```

### `SyncRequest`
```python
class SyncRequest(BaseModel):
    db_id: str
    replica_a_id: str
    replica_b_id: str
    tombstone_policy: Optional[str] = "FLAG_FOR_REVIEW" # "DELETE_WINS" | "UPDATE_RESURRECTS" | "FLAG_FOR_REVIEW"
```

---

## 3. Database Log Schema (`_ss_change_log`)

```sql
CREATE TABLE IF NOT EXISTS _ss_change_log (
    id           TEXT PRIMARY KEY,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    column_name  TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    ts_pt        REAL NOT NULL,
    ts_l         INTEGER NOT NULL DEFAULT 0,
    replica_id   TEXT NOT NULL,
    applied_at   TEXT NOT NULL,
    op_type      TEXT NOT NULL DEFAULT 'UPDATE'
);
```
