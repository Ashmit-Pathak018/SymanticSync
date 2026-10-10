"""
backend/api/routes_policies.py
────────────────────────────────
Policy configuration and validation endpoints.

Endpoints
---------
GET  /api/v1/databases/{db_id}/policies → List all policy assignments for a DB
PUT  /api/v1/databases/{db_id}/policies → Batch update policy assignments
POST /api/v1/validate-policy            → Pure policy/type validation (no side effects)
GET  /api/v1/policies/registry          → Full policy registry with descriptions
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.models import (
    PolicyAssignment,
    PolicyBatchUpdate,
    PolicyValidationRequest,
    PolicyValidationResult,
    ColumnSchema,
    TableSchema,
)
from backend.api.state import app_state
from backend.engine.policy_registry import list_policies
from backend.engine.policy_validator import PolicyValidator
from backend.engine.schema_inspector import SchemaInspector

router = APIRouter(tags=["Policies"])


# ─────────────────────────────────────────────────────────────
# GET /databases/{db_id}/policies
# ─────────────────────────────────────────────────────────────


@router.get(
    "/databases/{db_id}/policies",
    status_code=200,
)
def list_policies_for_db(db_id: str) -> list[dict]:
    """
    Return all policy assignments for *db_id*, merged with live schema info.

    Each item contains: table, column, normalized_type, policy (or null).
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
            detail=f"Database file missing at {info['path']!r}.",
        )

    db_policies = app_state.get_policies_for_db(db_id)
    result = []
    for table_name, columns in raw_schema.items():
        for col in columns:
            key = f"{table_name}:{col['name']}"
            result.append(
                {
                    "table": table_name,
                    "column": col["name"],
                    "normalized_type": col["normalized_type"],
                    "policy": db_policies.get(key),
                }
            )
    return result


# ─────────────────────────────────────────────────────────────
# PUT /databases/{db_id}/policies
# ─────────────────────────────────────────────────────────────


@router.put(
    "/databases/{db_id}/policies",
    status_code=200,
)
def update_policies(db_id: str, body: PolicyBatchUpdate) -> list[dict]:
    """
    Batch-assign policies to table/column pairs.

    Each assignment is validated against the column's normalised type
    (fetched live from the DB schema).  Returns 422 if ANY assignment is
    invalid — no partial saves are made on validation failure.

    Returns a list of PolicyValidationResult dicts (one per assignment).
    """
    info = app_state.get_db(db_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")

    # Build a normalised-type lookup for all columns
    try:
        inspector = SchemaInspector(info["path"])
        raw_schema = inspector.inspect_all()
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Database file missing at {info['path']!r}.",
        )

    type_lookup: dict[str, str] = {
        f"{tbl}:{col['name']}": col["normalized_type"]
        for tbl, cols in raw_schema.items()
        for col in cols
    }

    # Validate all assignments first — fail fast before any writes
    validation_results: list[dict] = []
    has_error = False

    for assignment in body.assignments:
        key = f"{assignment.table}:{assignment.column}"
        norm_type = type_lookup.get(key)
        if norm_type is None:
            result = PolicyValidationResult(
                valid=False,
                policy=assignment.policy,
                error_code="COLUMN_NOT_FOUND",
                error_message=(
                    f"Column '{assignment.column}' not found in table "
                    f"'{assignment.table}'."
                ),
            )
            has_error = True
        else:
            vr = PolicyValidator.validate(assignment.policy, norm_type)
            result = PolicyValidationResult(
                valid=vr.valid,
                policy=vr.policy,
                error_code=vr.error_code,
                error_message=vr.error_message,
            )
            if not vr.valid:
                has_error = True

        validation_results.append(result.model_dump())

    if has_error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "One or more policy assignments are invalid. No changes were saved.",
                "results": validation_results,
            },
        )

    # All valid — persist assignments
    for assignment in body.assignments:
        app_state.set_policy(
            db_id, assignment.table, assignment.column, assignment.policy.upper()
        )

    return validation_results


# ─────────────────────────────────────────────────────────────
# POST /validate-policy
# ─────────────────────────────────────────────────────────────


@router.post(
    "/validate-policy",
    response_model=PolicyValidationResult,
    status_code=200,
)
def validate_policy(body: PolicyValidationRequest) -> PolicyValidationResult:
    """
    Validate a single policy against a normalised type.

    Pure check — no state is modified.
    """
    vr = PolicyValidator.validate(body.policy, body.normalized_type)
    return PolicyValidationResult(
        valid=vr.valid,
        policy=vr.policy,
        error_code=vr.error_code,
        error_message=vr.error_message,
    )


# ─────────────────────────────────────────────────────────────
# GET /policies/registry
# ─────────────────────────────────────────────────────────────


@router.get("/policies/registry", status_code=200)
def get_policy_registry() -> list[dict]:
    """
    Return the full policy registry.

    Each entry contains: name, description, compatible_types, symmetric.
    """
    policies = list_policies()
    # Serialise the set of compatible_types as a sorted list for JSON output
    return [
        {
            **p,
            "compatible_types": sorted(p["compatible_types"]),
        }
        for p in policies
    ]
