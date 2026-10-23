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
    tombstone_policy: Optional[str] = Field(
        "FLAG_FOR_REVIEW",
        description="Policy for concurrent UPDATE vs DELETE: 'FLAG_FOR_REVIEW', 'DELETE_WINS', 'UPDATE_RESURRECTS'.",
    )


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
    """Development-only domain runner status; it is not a validated comparison."""

    workload: str
    evaluation_status: str = Field(
        "illustrative_unvalidated",
        description="This resolver-only domain runner is excluded from empirical comparisons.",
    )
    explanation: str
    baseline_scr: float | None = None
    semantic_sync_scr: float | None = None
    baseline_convergence_rate: float | None = None
    semantic_sync_convergence_rate: float | None = None
    resolution_overhead_ms: float | None = None
    total_conflicts_evaluated: int | None = None
    correct_semantic_outcomes: int | None = None


class StressBenchmarkRequest(BaseModel):
    """Body for POST /api/v1/benchmark/stress."""

    num_operations: int = Field(1000, description="1000, 5000, or 10000 operations.")
    conflict_density: float = Field(0.20, description="0, 0.05, 0.20, or 0.50 conflict density.")
    seed: int = Field(42, description="Random seed for reproducibility.")
    trials: int = Field(2, ge=2, le=10, description="Paired trials; system execution order alternates.")
    export_artifacts: bool = Field(True, description="Whether to export JSON/CSV benchmark artifacts.")


class StressBenchmarkMetrics(BaseModel):
    """Response model for POST /api/v1/benchmark/stress."""

    config: dict[str, Any]
    environment: dict[str, Any]
    num_operations: int
    conflict_density: float
    total_conflicts_evaluated: int
    baseline_scr: float | None
    semantic_sync_scr: float | None
    baseline_row_value_agreement_rate: float
    semantic_sync_row_value_agreement_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_latency_ms: float
    total_sync_time_ms: float
    resolution_overhead_ms: float = Field(
        ..., description="Legacy name for SemanticSync batch sync minus LWW batch sync; not resolver-only time."
    )
    change_log_entries: int
    artifacts: dict[str, str] = Field(default_factory=dict)
    baseline_vra: float | None = None
    semantic_sync_vra: float | None = None
    baseline_sync_time_ms: float = 0.0
    semantic_sync_sync_time_ms: float = 0.0
    baseline_change_log_entries: int = 0
    semantic_sync_change_log_entries: int = 0
    workload_digest: str = ""
    trial_count: int = 1
    summary_statistics: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Seed models
# ─────────────────────────────────────────────


class SeedRequest(BaseModel):
    """Body for POST /api/v1/seed — creates replicas and seeds conflict data."""

    workload: str = Field(
        ...,
        description="Workload identifier: 'inventory', 'notes', 'health', or 'all'.",
    )
