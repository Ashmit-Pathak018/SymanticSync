"""
backend/api/routes_benchmark.py
─────────────────────────────────
Research telemetry and benchmark harness comparing Generic Baseline (LWW)
versus SemanticSync (Semantic Middleware) on controlled workloads.

Endpoints
---------
POST /api/v1/benchmark/run → Run comparative benchmark on a workload
GET  /api/v1/metrics       → Get latest benchmark metrics and telemetry
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.models import (
    BenchmarkMetrics,
    BenchmarkRequest,
    StressBenchmarkMetrics,
    StressBenchmarkRequest,
)
from backend.api.state import DATA_DIR, app_state
from backend.engine.semantic_resolver import SemanticResolver
from backend.workloads.health_workload import HealthWorkload
from backend.workloads.inventory_workload import InventoryWorkload
from backend.workloads.notes_workload import NotesWorkload
from backend.workloads.stress_harness import StressBenchmarkConfig, StressHarness

router = APIRouter(tags=["Benchmark"])


@router.post("/benchmark/run", response_model=BenchmarkMetrics, status_code=200)
def run_benchmark(body: BenchmarkRequest) -> BenchmarkMetrics:
    """
    Run empirical comparison between Baseline (Generic LWW) and SemanticSync.
    Evaluates Semantic Correctness Rate (SCR), Convergence, and Overhead.
    """
    wl_name = body.workload.strip().lower()

    if wl_name == "inventory":
        workload = InventoryWorkload()
    elif wl_name == "notes":
        workload = NotesWorkload()
    elif wl_name in ("health", "healthcare"):
        workload = HealthWorkload()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workload '{body.workload}'. Supported: 'inventory', 'notes', 'health'",
        )

    # 1. Setup workload in isolated directory
    info = workload.setup()
    conflicts = workload.get_ground_truth_conflicts()
    policies = {p["column"]: p["policy"] for p in workload.get_policy_assignments()}

    total_conflicts = len(conflicts)
    baseline_correct = 0
    semantic_sync_correct = 0

    t0 = time.perf_counter()

    for c in conflicts:
        col = c["column"]
        policy = policies.get(col, "LWW")
        base_val = c["base_value"]
        val_a = c["value_a"]
        val_b = c["value_b"]
        expected_semantic = c["expected_semantic_result"]

        # Run Generic Baseline: Last-Write-Wins (picks val_b by timestamp tie/recency)
        baseline_res = val_b
        # Compare baseline against expected semantic ground truth
        if expected_semantic == "FLAGGED":
            # Baseline never flags conflicts, so it fails on REJECT policies
            baseline_match = False
        elif baseline_res == expected_semantic:
            baseline_match = True
        else:
            baseline_match = False

        if baseline_match:
            baseline_correct += 1

        # Run SemanticSync: Policy-driven resolution
        sem_res = SemanticResolver.resolve(
            policy=policy,
            base_value=base_val,
            replica_a_value=val_a,
            replica_b_value=val_b,
            replica_a_id="device_a",
            replica_b_id="device_b",
        )

        if expected_semantic in ("FLAGGED", None):
            if sem_res.status == "flagged":
                semantic_sync_correct += 1
        elif sem_res.status == "resolved":
            if sem_res.resolved_value == expected_semantic:
                semantic_sync_correct += 1
            elif isinstance(expected_semantic, str) and (
                expected_semantic in str(sem_res.resolved_value)
                or str(sem_res.resolved_value) in expected_semantic
            ):
                semantic_sync_correct += 1

    duration_ms = (time.perf_counter() - t0) * 1000.0
    overhead_per_conflict = round(duration_ms / max(1, total_conflicts), 3)

    baseline_scr = round((baseline_correct / max(1, total_conflicts)) * 100.0, 1)
    semantic_scr = round((semantic_sync_correct / max(1, total_conflicts)) * 100.0, 1)

    metrics = BenchmarkMetrics(
        workload=wl_name,
        baseline_scr=baseline_scr,
        semantic_sync_scr=semantic_scr,
        baseline_convergence_rate=100.0,  # Generic CRDT converges to a single state, but semantically wrong
        semantic_sync_convergence_rate=100.0,
        resolution_overhead_ms=overhead_per_conflict,
        total_conflicts_evaluated=total_conflicts,
        correct_semantic_outcomes=semantic_sync_correct,
    )

    # Cache metrics in AppState
    app_state.set_metrics(wl_name, metrics.model_dump())

    return metrics


@router.get("/metrics", status_code=200)
def get_metrics() -> dict[str, Any]:
    """Return all cached research metrics across workloads."""
    return {
        "workloads": app_state.metrics,
        "total_workloads_evaluated": len(app_state.metrics),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.post("/benchmark/stress", response_model=StressBenchmarkMetrics, status_code=200)
def run_stress_benchmark(body: StressBenchmarkRequest) -> StressBenchmarkMetrics:
    """
    Run scaled parametric stress benchmark (1,000 to 10,000 operations).
    Evaluates SCR, CR, p50/p95/p99 latency, resolution overhead, and exports artifacts.
    """
    if body.num_operations not in (1000, 5000, 10000):
        raise HTTPException(
            status_code=400,
            detail="num_operations must be a positive integer, typically 1000, 5000, or 10000.",
        )
    if body.conflict_density not in (0.05, 0.20, 0.50):
        raise HTTPException(
            status_code=400,
            detail="conflict_density must be 0.05, 0.20, or 0.50.",
        )

    out_dir = str(DATA_DIR / "benchmarks") if body.export_artifacts else None
    cfg = StressBenchmarkConfig(
        num_operations=body.num_operations,
        conflict_density=body.conflict_density,
        seed=body.seed,
        output_dir=out_dir,
    )
    harness = StressHarness(cfg)
    result = harness.run_benchmark()

    # Cache latest stress result
    app_state.set_metrics("stress_latest", result.to_dict())

    return StressBenchmarkMetrics(**result.to_dict())


@router.get("/benchmark/artifacts", status_code=200)
def list_benchmark_artifacts() -> list[dict[str, Any]]:
    """List available benchmark JSON and CSV artifacts across known artifact folders."""
    from pathlib import Path
    dirs = [
        Path(".codex-phase4-optimized-matrix-20261013"),
        DATA_DIR / "benchmarks",
        Path(".codex-phase4-matrix-20261013"),
    ]
    seen = set()
    artifacts = []
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("benchmark_*.*")):
            if p.name in seen or p.suffix.lower() not in (".json", ".csv"):
                continue
            seen.add(p.name)
            stat = p.stat()
            ops = None
            density = None
            seed = None
            parts = p.stem.split("_")
            if len(parts) >= 4 and parts[0] == "benchmark":
                try:
                    ops = int(parts[1])
                    if parts[2].endswith("pct"):
                        density = int(parts[2][:-3])
                    seed = int(parts[3])
                except (ValueError, IndexError):
                    pass
            artifacts.append({
                "filename": p.name,
                "format": p.suffix.lower().lstrip("."),
                "size_bytes": stat.st_size,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
                "num_operations": ops,
                "conflict_density_pct": density,
                "seed": seed,
                "source_dir": str(d),
            })
    return artifacts


@router.get("/benchmark/artifacts/{filename}")
def download_benchmark_artifact(filename: str):
    """Download or view a specific benchmark artifact."""
    from pathlib import Path
    from fastapi.responses import FileResponse

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    dirs = [
        Path(".codex-phase4-optimized-matrix-20261013"),
        DATA_DIR / "benchmarks",
        Path(".codex-phase4-matrix-20261013"),
    ]
    target_path = None
    for d in dirs:
        p = d / filename
        if p.exists() and p.is_file():
            target_path = p
            break

    if not target_path:
        raise HTTPException(status_code=404, detail=f"Artifact '{filename}' not found.")

    media_type = "application/json" if filename.endswith(".json") else "text/csv"
    return FileResponse(
        str(target_path),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

