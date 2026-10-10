# SemanticSync — Data Models Reference

**Version:** 1.0

---

## Engine Layer Data Models

These are internal Python dataclasses used by the engine layer.

### `ConflictInfo`
```python
@dataclass
class ConflictInfo:
    conflict_id: str        # UUID4 string
    table: str              # SQLite table name
    row_id: Any             # Primary key value (int or str)
    column: str             # Column name
    base_value: Any         # Common ancestor value
    replica_a_value: Any    # Value from Replica A
    replica_b_value: Any    # Value from Replica B
    replica_a_id: str       # Replica A logical name
    replica_b_id: str       # Replica B logical name
    replica_a_ts: float     # HLC timestamp for A's write
    replica_b_ts: float     # HLC timestamp for B's write
    detected_at: str        # ISO-8601 UTC string
```

### `ResolutionResult`
```python
@dataclass
class ResolutionResult:
    status: Literal["resolved", "flagged"]
    resolved_value: Any         # Merged value (None if flagged)
    policy: PolicyType | str    # Policy that produced this result
    explanation: str            # Human-readable merge rationale
    is_deterministic: bool      # Always True for all built-in policies
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
    applied_changes: list[dict]     # Each resolved conflict with value + policy
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

## API Layer Data Models (Pydantic)

These are used by FastAPI for request validation and response serialization.

### `DatabaseCreate` (Request)
```python
class DatabaseCreate(BaseModel):
    name: str
    path: str
    description: str = ""
```

### `DatabaseInfo` (Response)
```python
class DatabaseInfo(BaseModel):
    id: str
    name: str
    path: str
    description: str
    table_count: int
    created_at: str
```

### `ColumnSchema` (Response)
```python
class ColumnSchema(BaseModel):
    name: str
    raw_type: str
    normalized_type: str
    is_pk: bool
    notnull: bool
    default_value: Any
    policy: Optional[str]   # Currently assigned merge policy
```

### `PolicyAssignment` (Request)
```python
class PolicyAssignment(BaseModel):
    table: str
    column: str
    policy: str
```

### `PolicyValidationRequest` (Request)
```python
class PolicyValidationRequest(BaseModel):
    table: str
    column: str
    policy: str
    normalized_type: str
```

### `PolicyValidationResult` (Response)
```python
class PolicyValidationResult(BaseModel):
    valid: bool
    policy: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
```

### `ConflictDetectRequest` (Request)
```python
class ConflictDetectRequest(BaseModel):
    db_id: str
    replica_a_id: str
    replica_b_id: str
```

### `ConflictResolveRequest` (Request)
```python
class ConflictResolveRequest(BaseModel):
    conflict_id: str
    resolution_mode: str   # auto | pick_a | pick_b | custom
    custom_value: Optional[Any] = None
```

### `SyncRequest` (Request)
```python
class SyncRequest(BaseModel):
    db_id: str
    replica_a_id: str
    replica_b_id: str
```

### `QueryRequest` (Request)
```python
class QueryRequest(BaseModel):
    db_id: str
    replica_id: Optional[str] = None
    sql: str
```

### `QueryResult` (Response)
```python
class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    duration_ms: float
```

### `BenchmarkMetrics` (Response)
```python
class BenchmarkMetrics(BaseModel):
    workload: str
    baseline_scr: float
    semantic_sync_scr: float
    baseline_convergence_rate: float
    semantic_sync_convergence_rate: float
    resolution_overhead_ms: float
    total_conflicts_evaluated: int
    correct_semantic_outcomes: int
```

### `SeedRequest` (Request)
```python
class SeedRequest(BaseModel):
    workload: str   # inventory | notes | health | all
```

---

## AppState Persistence Schema

`data/registry.json` structure:

```json
{
  "databases": {
    "db_inventory": {
      "id": "db_inventory",
      "name": "Inventory Workspace",
      "path": "data/inventory/inventory.db",
      "description": "...",
      "table_count": 1,
      "created_at": "2026-10-10T12:00:00Z"
    }
  },
  "replicas": {
    "inventory_device_a": {
      "replica_id": "inventory_device_a",
      "db_path": "data/inventory/inventory_device_a.db",
      "parent_db_id": "db_inventory",
      "created_at": "..."
    }
  },
  "policies": {
    "db_inventory:products:quantity": "SUM",
    "db_inventory:products:description": "APPEND",
    "db_inventory:products:sku": "REJECT"
  },
  "conflicts": {
    "uuid4": {
      "conflict_id": "uuid4",
      "db_id": "db_inventory",
      "table": "products",
      "row_id": 1,
      "column": "quantity",
      "base_value": 100,
      "value_a": 115,
      "value_b": 120,
      "status": "resolved",
      "resolved_value": 135,
      "policy": "SUM",
      "explanation": "SUM additive merge: ...",
      "detected_at": "...",
      "resolved_at": "..."
    }
  },
  "metrics": {
    "inventory": {
      "workload": "inventory",
      "baseline_scr": 33.3,
      "semantic_sync_scr": 100.0,
      ...
    }
  }
}
```
