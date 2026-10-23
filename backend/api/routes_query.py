"""
backend/api/routes_query.py
────────────────────────────
SQL Console execution endpoint for inspecting and querying database and replica states.

Endpoints
---------
POST /api/v1/query → Run SQLite SQL queries against base database or a replica
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.models import QueryRequest, QueryResult
from backend.api.state import app_state
from backend.engine.fk_quarantine import connect_with_foreign_keys

router = APIRouter(tags=["Query"])


@router.post("/query", response_model=QueryResult, status_code=200)
def execute_query(body: QueryRequest) -> QueryResult:
    """
    Execute standard SQLite SQL (SELECT, INSERT, UPDATE, PRAGMA, EXPLAIN).
    Target can be the registered base database or any of its replicas.

    SQL-console writes are intentionally outside tracked replication and
    checkpoint locking: they do not create operation identities or quarantine
    records. They are an unsupported mutation path for replica convergence.
    """
    db_path = None
    if body.replica_id:
        db_path = app_state.get_replica_path(body.replica_id)
        if not db_path:
            raise HTTPException(status_code=404, detail=f"Replica '{body.replica_id}' not found.")
    else:
        db_info = app_state.get_db(body.db_id)
        if not db_info:
            raise HTTPException(status_code=404, detail=f"Database '{body.db_id}' not found.")
        db_path = db_info["path"]

    sql = body.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query string cannot be empty.")
    if sql.lstrip().casefold().startswith("pragma foreign_keys"):
        raise HTTPException(status_code=400, detail="Foreign-key enforcement cannot be disabled through the SQL console.")

    t0 = time.perf_counter()
    try:
        conn = connect_with_foreign_keys(db_path, check_same_thread=False)
        if not body.replica_id and not body.allow_write:
            # Enforce the QueryRequest contract in SQLite itself so CTEs or
            # other statement forms cannot bypass a keyword-based write check.
            conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
            # Convert row tuples to list of serializable values
            rows = [list(r) for r in raw_rows]
        else:
            columns = ["affected_rows"]
            rows = [[cursor.rowcount]]
            conn.commit()

        conn.close()
        duration_ms = (time.perf_counter() - t0) * 1000.0

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows) if cursor.description else cursor.rowcount,
            duration_ms=round(duration_ms, 2),
        )
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"SQLite execution error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")
