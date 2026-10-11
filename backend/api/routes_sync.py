"""
backend/api/routes_sync.py
───────────────────────────
Replica synchronization triggers, simulation, and status.

Endpoints
---------
GET  /api/v1/sync/status             → Synchronization status and counts
POST /api/v1/sync/run                → Execute replica sync pipeline
POST /api/v1/sync/generate-conflict  → Inject controlled divergent edit across replicas
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.models import SyncRequest
from backend.api.state import app_state
from backend.engine.crdt_sync import CRDTSyncEngine

router = APIRouter(tags=["Sync"])
_sync_engine = CRDTSyncEngine()


class ConflictGenerateRequest(BaseModel):
    db_id: str
    replica_a_id: str
    replica_b_id: str
    table: str
    row_id: Any
    column: str
    value_a: Any
    value_b: Any


@router.get("/sync/status", status_code=200)
def sync_status() -> dict[str, Any]:
    """Return synchronization overview and pending conflict stats."""
    conflicts = list(app_state.conflicts.values())
    pending = [c for c in conflicts if c.get("status") == "pending"]
    flagged = [c for c in conflicts if c.get("status") == "flagged"]
    resolved = [c for c in conflicts if c.get("status") == "resolved"]

    return {
        "status": "ready",
        "registered_databases": len(app_state.databases),
        "registered_replicas": len(app_state.replicas),
        "total_conflicts": len(conflicts),
        "pending_conflicts": len(pending),
        "flagged_conflicts": len(flagged),
        "resolved_conflicts": len(resolved),
        "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.post("/sync/run", status_code=200)
def run_sync(body: SyncRequest) -> dict[str, Any]:
    """
    Execute three-way synchronization between replica A and replica B against their base database.
    Applies schema policies to resolve divergent updates deterministically.
    """
    db_info = app_state.get_db(body.db_id)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Database '{body.db_id}' not found.")

    base_path = db_info["path"]
    rep_a_path = app_state.get_replica_path(body.replica_a_id)
    rep_b_path = app_state.get_replica_path(body.replica_b_id)

    if not rep_a_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_a_id}' not found.")
    if not rep_b_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_b_id}' not found.")

    # Retrieve policies formatted as {table: {column: policy}}
    assigned_policies = app_state.get_policies_for_db(body.db_id)
    nested_policies: dict[str, dict[str, str]] = {}
    for key, pol in assigned_policies.items():
        # key format is "table:column"
        parts = key.split(":")
        if len(parts) == 2:
            tbl, col = parts
            nested_policies.setdefault(tbl, {})[col] = pol

    # Set table-level tombstone policy if provided
    tombstone_pol = getattr(body, "tombstone_policy", "FLAG_FOR_REVIEW") or "FLAG_FOR_REVIEW"
    for tbl in list(nested_policies.keys()):
        nested_policies[tbl]["__tombstone__"] = tombstone_pol

    result = _sync_engine.sync_replicas(
        replica_a_path=rep_a_path,
        replica_b_path=rep_b_path,
        base_path=base_path,
        replica_a_id=body.replica_a_id,
        replica_b_id=body.replica_b_id,
        policies=nested_policies,
    )

    # Sync any newly generated conflicts with app_state
    for change in result.applied_changes:
        cid = change.get("conflict_id")
        if cid:
            rec = app_state.get_conflict(cid) or {}
            rec.update(
                {
                    "conflict_id": cid,
                    "db_id": body.db_id,
                    "table": change.get("table"),
                    "row_id": change.get("row_id"),
                    "column": change.get("column"),
                    "status": "resolved",
                    "resolved_value": change.get("resolved_value"),
                    "policy": change.get("policy"),
                    "explanation": change.get("explanation"),
                    "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            app_state.store_conflict(cid, rec)

    return {
        "status": "completed",
        "total_conflicts": result.total_conflicts,
        "auto_resolved": result.auto_resolved,
        "flagged_for_review": result.flagged_for_review,
        "applied_changes": result.applied_changes,
        "flagged_conflicts": result.flagged_conflicts,
        "duration_ms": round(result.duration_ms, 2),
    }


@router.post("/sync/generate-conflict", status_code=200)
def generate_conflict(body: ConflictGenerateRequest) -> dict[str, Any]:
    """
    Simulation utility: writes divergent values to Replica A and Replica B to test conflict resolution.
    """
    rep_a_path = app_state.get_replica_path(body.replica_a_id)
    rep_b_path = app_state.get_replica_path(body.replica_b_id)

    if not rep_a_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_a_id}' not found.")
    if not rep_b_path:
        raise HTTPException(status_code=404, detail=f"Replica '{body.replica_b_id}' not found.")

    change_a = _sync_engine.apply_change(
        replica_db_path=rep_a_path,
        replica_id=body.replica_a_id,
        table=body.table,
        row_id=body.row_id,
        column=body.column,
        new_value=body.value_a,
    )

    change_b = _sync_engine.apply_change(
        replica_db_path=rep_b_path,
        replica_id=body.replica_b_id,
        table=body.table,
        row_id=body.row_id,
        column=body.column,
        new_value=body.value_b,
    )

    return {
        "status": "divergence_injected",
        "table": body.table,
        "row_id": body.row_id,
        "column": body.column,
        "replica_a_change_id": change_a,
        "replica_b_change_id": change_b,
    }
