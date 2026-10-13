"""
routes_quarantine.py
====================
Phase 5: REST API endpoints for inspecting and resolving quarantined rows.

Endpoints
---------
GET  /api/v1/quarantine              — List quarantined rows (filter by table, status)
GET  /api/v1/quarantine/{qid}        — Get single quarantine record
POST /api/v1/quarantine/{qid}/resolve — Mark record resolved (confirmed_deleted | relinked)
"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.state import app_state
from backend.engine.fk_quarantine import (
    connect_with_foreign_keys,
    ensure_quarantine_table,
    list_quarantined,
    resolve_quarantine_record,
)
from backend.engine.mutation_lock import serialized_mutation

router = APIRouter(tags=["Quarantine"])


class QuarantineResolveRequest(BaseModel):
    action: str = "confirmed_deleted"  # or "relinked"
    new_parent_row_id: Any | None = None


def _open_quarantine_conn(db_path: str) -> sqlite3.Connection:
    conn = connect_with_foreign_keys(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_quarantine_table(conn)
    return conn


@router.get("/quarantine", status_code=200)
def list_quarantine(
    table: str | None = None,
    status: str | None = None,
    db_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    List all quarantined rows across the base database (or a specified replica).

    Query parameters
    ----------------
    table   Filter by ``table_name``.
    status  Filter by ``status`` (e.g. ``quarantined``, ``confirmed_deleted``, ``relinked``).
    db_id   Database ID from the registry (defaults to the first registered DB).
    """
    if db_id:
        db_path = app_state.get_db_path(db_id)
    else:
        # Use first registered DB or raise
        db_path = next(iter(app_state.databases.values()), {}).get("path") if app_state.databases else None

    if not db_path:
        raise HTTPException(status_code=404, detail="No database registered. Register a database first.")

    conn = _open_quarantine_conn(db_path)
    try:
        records = list_quarantined(conn, table_name=table, status=status)
    finally:
        conn.close()
    return records


@router.get("/quarantine/{quarantine_id}", status_code=200)
def get_quarantine_record(quarantine_id: str, db_id: str | None = None) -> dict[str, Any]:
    """Get a single quarantine record by ID."""
    if db_id:
        db_path = app_state.get_db_path(db_id)
    else:
        db_path = next(iter(app_state.databases.values()), {}).get("path") if app_state.databases else None

    if not db_path:
        raise HTTPException(status_code=404, detail="No database registered.")

    conn = _open_quarantine_conn(db_path)
    try:
        records = list_quarantined(conn)
        match = next((r for r in records if r["quarantine_id"] == quarantine_id), None)
    finally:
        conn.close()

    if match is None:
        raise HTTPException(status_code=404, detail=f"Quarantine record '{quarantine_id}' not found.")
    return match


@router.post("/quarantine/{quarantine_id}/resolve", status_code=200)
@serialized_mutation
def resolve_quarantine(
    quarantine_id: str,
    body: QuarantineResolveRequest,
    db_id: str | None = None,
) -> dict[str, Any]:
    """
    Mark a quarantine record as resolved.

    ``action`` options:
    - ``confirmed_deleted`` — parent deletion was intentional; child can be discarded.
    - ``relinked`` — caller has re-inserted the child under a new parent.
    """
    valid_actions = {"confirmed_deleted", "relinked"}
    if body.action not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"action must be one of {sorted(valid_actions)}",
        )

    if db_id:
        db_path = app_state.get_db_path(db_id)
    else:
        db_path = next(iter(app_state.databases.values()), {}).get("path") if app_state.databases else None

    if not db_path:
        raise HTTPException(status_code=404, detail="No database registered.")

    conn = _open_quarantine_conn(db_path)
    try:
        with conn:
            ok = resolve_quarantine_record(conn, quarantine_id, action=body.action,
                                           new_parent_row_id=body.new_parent_row_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Quarantine record '{quarantine_id}' not found.")
        records = list_quarantined(conn)
        updated = next((r for r in records if r["quarantine_id"] == quarantine_id), None)
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()

    return updated or {"quarantine_id": quarantine_id, "status": body.action}
