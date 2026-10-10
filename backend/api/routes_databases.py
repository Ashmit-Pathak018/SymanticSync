"""
backend/api/routes_databases.py
─────────────────────────────────
Database workspace management endpoints.

Endpoints
---------
GET  /api/v1/databases                  → List all registered databases
POST /api/v1/databases                  → Register a new database
GET  /api/v1/databases/{db_id}          → Get database info
GET  /api/v1/databases/{db_id}/schema   → Introspect schema + policies
POST /api/v1/databases/{db_id}/replicas → Create a replica
GET  /api/v1/databases/{db_id}/replicas → List replicas for a database
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.models import (
    DatabaseCreate,
    DatabaseInfo,
    DatabaseSchema,
    ReplicaInfo,
    TableSchema,
    ColumnSchema,
)
from backend.api.state import app_state
from backend.engine.schema_inspector import SchemaInspector
from backend.engine.crdt_sync import CRDTSyncEngine

router = APIRouter(tags=["Databases"])
_sync_engine = CRDTSyncEngine()


# ─────────────────────────────────────────────────────────────
# GET /databases
# ─────────────────────────────────────────────────────────────


@router.get("/databases", response_model=list[DatabaseInfo], status_code=200)
def list_databases() -> list[DatabaseInfo]:
    """Return all registered databases."""
    return [DatabaseInfo(**db) for db in app_state.list_databases()]


# ─────────────────────────────────────────────────────────────
# POST /databases
# ─────────────────────────────────────────────────────────────


@router.post("/databases", response_model=DatabaseInfo, status_code=201)
def register_database(body: DatabaseCreate) -> DatabaseInfo:
    """
    Register a new SQLite database by path.

    Validates the file is readable before registering.
    Returns 400 if the file does not exist or is not a valid SQLite DB.
    """
    try:
        inspector = SchemaInspector(body.path)
        table_count = inspector.table_count()
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Database file not found: {body.path!r}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not open SQLite database at {body.path!r}: {exc}",
        )

    db_id = str(uuid.uuid4())
    info: dict[str, Any] = {
        "id": db_id,
        "name": body.name,
        "path": body.path,
        "description": body.description,
        "table_count": table_count,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    app_state.register_db(db_id, info)
    return DatabaseInfo(**info)


# ─────────────────────────────────────────────────────────────
# GET /databases/{db_id}
# ─────────────────────────────────────────────────────────────


@router.get("/databases/{db_id}", response_model=DatabaseInfo, status_code=200)
def get_database(db_id: str) -> DatabaseInfo:
    """Return info for a single registered database. 404 if not found."""
    info = app_state.get_db(db_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")
    return DatabaseInfo(**info)


# ─────────────────────────────────────────────────────────────
# GET /databases/{db_id}/schema
# ─────────────────────────────────────────────────────────────


@router.get(
    "/databases/{db_id}/schema",
    response_model=DatabaseSchema,
    status_code=200,
)
def get_schema(db_id: str) -> DatabaseSchema:
    """
    Introspect schema for a registered database.

    Merges active policy assignments from AppState into each ColumnSchema.
    """
    info = app_state.get_db(db_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")

    try:
        inspector = SchemaInspector(info["path"])
        raw_schema = inspector.inspect_all()
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Database file not found at {info['path']!r}. Was it moved?",
        )

    db_policies = app_state.get_policies_for_db(db_id)
    # db_policies keys are "table:column"

    tables: list[TableSchema] = []
    for table_name, columns in raw_schema.items():
        col_schemas = [
            ColumnSchema(
                **col,
                policy=db_policies.get(f"{table_name}:{col['name']}"),
            )
            for col in columns
        ]
        tables.append(TableSchema(table_name=table_name, columns=col_schemas))

    return DatabaseSchema(db_id=db_id, tables=tables)


# ─────────────────────────────────────────────────────────────
# POST /databases/{db_id}/replicas
# ─────────────────────────────────────────────────────────────


class _ReplicaCreateBody:
    """Inline body model (not worth a top-level Pydantic class)."""
    pass


from pydantic import BaseModel as _BM


class _ReplicaCreateRequest(_BM):
    replica_id: str


@router.post(
    "/databases/{db_id}/replicas",
    response_model=ReplicaInfo,
    status_code=201,
)
def create_replica(db_id: str, body: _ReplicaCreateRequest) -> ReplicaInfo:
    """
    Create a replica of the registered database.

    Copies the base .db file to ``data/<replica_id>.db``.
    Returns 404 if *db_id* is not registered.
    Returns 400 if the base DB file cannot be found on disk.
    """
    info = app_state.get_db(db_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")

    replica_id = body.replica_id.strip()
    if not replica_id:
        raise HTTPException(status_code=400, detail="replica_id must not be empty.")

    try:
        replica_path = _sync_engine.create_replica(info["path"], replica_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create replica: {exc}")

    replica_info: dict[str, Any] = {
        "replica_id": replica_id,
        "db_path": replica_path,
        "parent_db_id": db_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    app_state.register_replica(replica_id, replica_info)
    return ReplicaInfo(**replica_info)


# ─────────────────────────────────────────────────────────────
# GET /databases/{db_id}/replicas
# ─────────────────────────────────────────────────────────────


@router.get(
    "/databases/{db_id}/replicas",
    response_model=list[ReplicaInfo],
    status_code=200,
)
def list_replicas(db_id: str) -> list[ReplicaInfo]:
    """List all replicas for a given database. 404 if db_id unknown."""
    if app_state.get_db(db_id) is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")
    return [ReplicaInfo(**r) for r in app_state.list_replicas_for_db(db_id)]
