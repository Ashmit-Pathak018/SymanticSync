"""
backend/api/models.py
─────────────────────
Pydantic v2 request / response schemas for all SemanticSync REST endpoints.
No domain logic lives here — these are pure data-transfer objects.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Database models
# ─────────────────────────────────────────────


class DatabaseCreate(BaseModel):
    """Body for POST /api/v1/databases — registers a new SQLite DB."""

    name: str = Field(..., description="Human-readable workspace name.")
    path: str = Field(..., description="Absolute or relative path to the .db file.")
    description: str = Field("", description="Optional free-text description.")


class DatabaseInfo(BaseModel):
    """Full info record returned for a registered database."""

    id: str
    name: str
    path: str
    description: str
    table_count: int
    created_at: str


class ReplicaInfo(BaseModel):
    """Metadata for a single replica of a registered database."""

    replica_id: str
    db_path: str
    parent_db_id: str
    created_at: str


# ─────────────────────────────────────────────
# Schema models
# ─────────────────────────────────────────────


class ColumnSchema(BaseModel):
    """Introspected column metadata, enriched with the active merge policy."""

    name: str
    raw_type: str
    normalized_type: str
    is_pk: bool
    notnull: bool
    default_value: Any
    policy: Optional[str] = Field(None, description="Currently assigned merge policy.")


class TableSchema(BaseModel):
    """All columns for a single table."""

    table_name: str
    columns: list[ColumnSchema]


class DatabaseSchema(BaseModel):
    """Complete schema for a registered database, including policy assignments."""

    db_id: str
    tables: list[TableSchema]


# ─────────────────────────────────────────────
# Policy models
# ─────────────────────────────────────────────


class PolicyAssignment(BaseModel):
    """A single table-column → policy mapping."""

    table: str
    column: str
    policy: str = Field(..., description="Policy name, e.g. 'SUM', 'AVG', 'APPEND'.")


class PolicyBatchUpdate(BaseModel):
    """Body for PUT /api/v1/databases/{db_id}/policies."""

    assignments: list[PolicyAssignment]


class PolicyValidationRequest(BaseModel):
    """Body for POST /api/v1/validate-policy — pure validation, no side effects."""

    table: str
    column: str
    policy: str
    normalized_type: str


class PolicyValidationResult(BaseModel):
    """Validation outcome for a single policy assignment."""

    valid: bool
    policy: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ─────────────────────────────────────────────
# Conflict models
# ─────────────────────────────────────────────


class ConflictDetectRequest(BaseModel):
    """Body for POST /api/v1/conflicts/detect."""

    db_id: str
    replica_a_id: str
    replica_b_id: str


class ConflictResolveRequest(BaseModel):
    """Body for POST /api/v1/conflicts/resolve."""

    conflict_id: str
    resolution_mode: str = Field(
        ...,
        description="One of: 'auto', 'pick_a', 'pick_b', 'custom'.",
    )
    custom_value: Optional[Any] = Field(
        None,
        description="Used only when resolution_mode == 'custom'.",
    )


# ─────────────────────────────────────────────
# Sync models
# ─────────────────────────────────────────────


class SyncRequest(BaseModel):
    """Body for POST /api/v1/sync/run."""

    db_id: str
    replica_a_id: str
    replica_b_id: str


class GenerateConflictRequest(BaseModel):
    """Body for POST /api/v1/sync/generate-conflict — simulates divergent edits."""

    db_id: str
    replica_a_id: str
    replica_b_id: str
    table: str
    row_id: Any
    column: str
    value_a: Any
    value_b: Any


# ─────────────────────────────────────────────
# Query models
# ─────────────────────────────────────────────


class QueryRequest(BaseModel):
    """Body for POST /api/v1/query — executes raw SQL against a DB or replica."""

    db_id: str
    replica_id: Optional[str] = Field(
        None,
        description="If omitted, the query targets the base DB.",
    )
    sql: str
    allow_write: bool = Field(
        False,
        description="Must be True to run INSERT/UPDATE/DELETE against the base DB.",
    )


class QueryResult(BaseModel):
    """Result of a raw SQL query execution."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    duration_ms: float


# ─────────────────────────────────────────────
# Benchmark models
# ─────────────────────────────────────────────


class BenchmarkRequest(BaseModel):
    """Body for POST /api/v1/benchmark/run."""

    workload: str = Field(
        ..., description="One of: 'inventory', 'notes', 'health'."
    )


class BenchmarkMetrics(BaseModel):
    """Comparative evaluation metrics: SemanticSync vs. generic LWW baseline."""

    workload: str
    baseline_scr: float = Field(..., description="Semantic Correctness Rate for LWW baseline.")
    semantic_sync_scr: float = Field(..., description="Semantic Correctness Rate for SemanticSync.")
    baseline_convergence_rate: float
    semantic_sync_convergence_rate: float
    resolution_overhead_ms: float
    total_conflicts_evaluated: int
    correct_semantic_outcomes: int


# ─────────────────────────────────────────────
# Seed models
# ─────────────────────────────────────────────


class SeedRequest(BaseModel):
    """Body for POST /api/v1/seed — creates replicas and seeds conflict data."""

    workload: str = Field(
        ...,
        description="Workload identifier: 'inventory', 'notes', 'health', or 'all'.",
    )
