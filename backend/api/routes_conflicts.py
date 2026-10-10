"""
backend/api/routes_conflicts.py
────────────────────────────────
Endpoints for conflict inspection and manual/automatic resolution.

Endpoints
---------
POST /api/v1/conflicts/detect   → Detect conflicts across two replicas
POST /api/v1/conflicts/resolve  → Resolve a conflict (auto, pick_a, pick_b, custom)
GET  /api/v1/conflicts          → List all detected conflicts (filterable)
GET  /api/v1/conflicts/{id}     → Get details of a single conflict
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.api.models import (
    ConflictDetectRequest,
    ConflictResolveRequest,
)
from backend.api.state import app_state
from backend.engine.conflict_detector import ConflictDetector
from backend.engine.merge_manager import MergeManager
from backend.engine.semantic_resolver import SemanticResolver, ResolutionError

router = APIRouter(tags=["Conflicts"])
_detector = ConflictDetector()
_manager = MergeManager(app_state=app_state)


@router.post("/conflicts/detect", status_code=200)
def detect_conflicts(body: ConflictDetectRequest) -> list[dict[str, Any]]:
    """
    Run three-way diff between replica A, replica B, and base database.
    Persists detected conflicts into the conflict store.
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

    conflicts = _detector.detect(
        replica_a_db=rep_a_path,
        replica_b_db=rep_b_path,
        base_db=base_path,
        replica_a_id=body.replica_a_id,
        replica_b_id=body.replica_b_id,
    )

    records = []
    for c in conflicts:
        rec = {
            "conflict_id": c.conflict_id,
            "db_id": body.db_id,
            "table": c.table,
            "row_id": c.row_id,
            "column": c.column,
            "base_value": c.base_value,
            "value_a": c.replica_a_value,
            "value_b": c.replica_b_value,
            "replica_a_id": c.replica_a_id,
            "replica_b_id": c.replica_b_id,
            "replica_a_ts": c.replica_a_ts,
            "replica_b_ts": c.replica_b_ts,
            "status": "pending",
            "detected_at": c.detected_at,
            "policy": app_state.get_policy(body.db_id, c.table, c.column) or "REJECT",
        }
        _manager.add_conflict(rec)
        records.append(rec)

    return records


@router.post("/conflicts/resolve", status_code=200)
def resolve_conflict(body: ConflictResolveRequest) -> dict[str, Any]:
    """
    Resolve a specific conflict.
    resolution_mode: 'auto', 'pick_a', 'pick_b', 'custom'
    """
    record = app_state.get_conflict(body.conflict_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Conflict '{body.conflict_id}' not found.")

    mode = body.resolution_mode.strip().lower()

    if mode == "pick_a":
        resolved_value = record.get("value_a")
        status = "resolved"
        explanation = f"Manual resolution: picked Replica A value ({resolved_value!r})"
    elif mode == "pick_b":
        resolved_value = record.get("value_b")
        status = "resolved"
        explanation = f"Manual resolution: picked Replica B value ({resolved_value!r})"
    elif mode == "custom":
        resolved_value = body.custom_value
        status = "resolved"
        explanation = f"Manual resolution: custom value applied ({resolved_value!r})"
    elif mode == "auto":
        db_id = record.get("db_id")
        table = record.get("table")
        column = record.get("column")
        policy = app_state.get_policy(db_id, table, column) if db_id else record.get("policy", "REJECT")
        if not policy:
            policy = record.get("policy", "REJECT")

        try:
            res = SemanticResolver.resolve(
                policy=policy,
                base_value=record.get("base_value"),
                replica_a_value=record.get("value_a"),
                replica_b_value=record.get("value_b"),
                replica_a_id=record.get("replica_a_id", "replica_a"),
                replica_b_id=record.get("replica_b_id", "replica_b"),
                replica_a_ts=record.get("replica_a_ts"),
                replica_b_ts=record.get("replica_b_ts"),
            )
            resolved_value = res.resolved_value
            status = res.status
            explanation = res.explanation
        except ResolutionError as e:
            raise HTTPException(status_code=400, detail=f"Policy resolution failed: {e}")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution_mode '{mode}'. Must be one of: 'auto', 'pick_a', 'pick_b', 'custom'",
        )

    # Write-back to replicas if resolved
    if status == "resolved" and resolved_value is not None:
        for rep_key in ("replica_a_id", "replica_b_id"):
            rep_id = record.get(rep_key)
            if rep_id:
                rep_path = app_state.get_replica_path(rep_id)
                if rep_path:
                    import sqlite3
                    try:
                        with sqlite3.connect(rep_path) as conn:
                            conn.execute(
                                f'UPDATE "{record["table"]}" SET "{record["column"]}" = ? WHERE id = ?',
                                (resolved_value, record["row_id"]),
                            )
                            conn.commit()
                    except Exception:
                        pass

    record["status"] = status
    record["resolved_value"] = resolved_value
    record["resolution_mode"] = mode
    record["explanation"] = explanation
    record["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    app_state.store_conflict(body.conflict_id, record)
    _manager.apply_resolution(body.conflict_id, record)

    return {
        "status": status,
        "result": resolved_value,
        "policy": record.get("policy"),
        "explanation": explanation,
        "conflict": record,
    }


@router.get("/conflicts", status_code=200)
def list_conflicts(
    status: Optional[str] = Query(None, description="Filter by pending, resolved, flagged"),
    db_id: Optional[str] = Query(None, description="Filter by db_id"),
) -> list[dict[str, Any]]:
    """List detected conflicts."""
    all_conflicts = list(app_state.conflicts.values())
    if db_id:
        all_conflicts = [c for c in all_conflicts if c.get("db_id") == db_id]
    if status and status != "all":
        all_conflicts = [c for c in all_conflicts if c.get("status") == status]
    return all_conflicts


@router.get("/conflicts/{conflict_id}", status_code=200)
def get_conflict(conflict_id: str) -> dict[str, Any]:
    """Get single conflict record."""
    c = app_state.get_conflict(conflict_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Conflict '{conflict_id}' not found.")
    return c
