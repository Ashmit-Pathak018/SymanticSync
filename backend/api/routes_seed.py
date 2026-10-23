"""
backend/api/routes_seed.py
──────────────────────────
Demo seeding endpoint to populate realistic workloads and replicas.

Endpoints
---------
POST /api/v1/seed → Seed Inventory, Collaboration Notes, or Healthcare demo databases
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.models import SeedRequest
from backend.api.state import DATA_DIR, app_state
from backend.workloads.health_workload import HealthWorkload, seed as seed_health
from backend.workloads.inventory_workload import InventoryWorkload, seed as seed_inv
from backend.workloads.notes_workload import NotesWorkload, seed as seed_notes

router = APIRouter(tags=["Seed"])


@router.post("/seed", status_code=200)
def seed_workload(body: SeedRequest) -> dict[str, Any]:
    """
    Seed a demo workload: creates base SQLite DB, forks 3 replicas (device_a, device_b, device_c),
    configures recommended semantic policies, and registers the workspace.
    """
    wl = body.workload.strip().lower()
    targets = ["inventory", "notes", "health"] if wl == "all" else [wl]

    if app_state.registry_load_error:
        raise HTTPException(
            status_code=409,
            detail=f"Demo seeding is blocked because persisted application state is not trusted: {app_state.registry_load_error}",
        )

    if any(name not in {"inventory", "notes", "health"} for name in targets):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workload '{wl}'. Choose from 'inventory', 'notes', 'health', or 'all'.",
        )

    # Seeders replace the known sample rows. Refuse to run against an existing
    # demo dataset so old tracked history cannot be paired with reset values.
    existing = []
    for name in targets:
        target_dir = DATA_DIR / name
        paths = [target_dir / f"{name}.db"] + [
            target_dir / f"{name}_device_{suffix}.db" for suffix in ("a", "b", "c")
        ]
        if app_state.get_db(f"db_{name}") or any(path.exists() for path in paths):
            existing.append(name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Demo workload(s) already exist: {', '.join(existing)}. Seeding replaces sample rows, "
                "so use a fresh SEMANTICSYNC_DATA_DIR for a clean demo instead of reseeding this directory."
            ),
        )

    created = []

    for name in targets:
        target_dir = DATA_DIR / name
        target_dir.mkdir(parents=True, exist_ok=True)

        base_path = str(target_dir / f"{name}.db")
        replica_paths = {
            f"{name}_device_a": str(target_dir / f"{name}_device_a.db"),
            f"{name}_device_b": str(target_dir / f"{name}_device_b.db"),
            f"{name}_device_c": str(target_dir / f"{name}_device_c.db"),
        }

        # 1. Run seeder
        if name == "inventory":
            summary = seed_inv(base_path, replica_paths)
            db_desc = "E-Commerce inventory stock, prices, descriptions, and SKU policies"
        elif name == "notes":
            summary = seed_notes(base_path, replica_paths)
            db_desc = "Collaborative document editor with body appends, edit counts, and author tracking"
        elif name == "health":
            summary = seed_health(base_path, replica_paths)
            db_desc = "Healthcare illustrative workload: vital signs AVG, notes APPEND, blood type REJECT"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown workload '{name}'. Choose from 'inventory', 'notes', 'health', 'all'.",
            )

        # 2. Register base DB in AppState
        db_id = f"db_{name}"
        app_state.register_db(
            db_id=db_id,
            name=f"{name.capitalize()} Workspace",
            path=base_path,
            description=db_desc,
        )

        # 3. Register replicas in AppState
        for rep_id, r_path in replica_paths.items():
            app_state.register_replica(
                replica_id=rep_id,
                db_path=r_path,
                parent_db_id=db_id,
            )

        # 4. Assign recommended policies in AppState
        for p in summary["suggested_policies"]:
            app_state.set_policy(
                db_id=db_id,
                table=p["table"],
                column=p["column"],
                policy=p["policy"],
            )

        created.append(
            {
                "db_id": db_id,
                "name": name,
                "base_path": base_path,
                "replicas": list(replica_paths.keys()),
                "policies_assigned": len(summary["suggested_policies"]),
            }
        )

    return {
        "status": "seeded",
        "workloads_created": created,
    }
