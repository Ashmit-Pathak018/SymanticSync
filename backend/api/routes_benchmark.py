"""
backend/api/routes_benchmark.py
─────────────────────────────────
Stress benchmark telemetry and a clearly unvalidated domain-runner status.

Endpoints
---------
POST /api/v1/benchmark/run → Return status for the unvalidated domain runner
GET  /api/v1/metrics       → Get latest benchmark metrics and telemetry
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.models import (
    BenchmarkMetrics,
    BenchmarkRequest,
    StressBenchmarkMetrics,
    StressBenchmarkRequest,
)
from backend.api.state import DATA_DIR, app_state
from backend.workloads.stress_harness import StressBenchmarkConfig, StressHarness

router = APIRouter(tags=["Benchmark"])


@router.post("/benchmark/run", response_model=BenchmarkMetrics, status_code=200)
def run_benchmark(body: BenchmarkRequest) -> BenchmarkMetrics:
    """
    Return a development-only domain runner status, without comparative metrics.

    The former implementation compared a replica-B value proxy with direct
    resolver calls and emitted placeholder convergence values. It did not run
    replica synchronization, so those numbers are no longer exposed as results.
    """
    wl_name = body.workload.strip().lower()
    supported = {"inventory": "inventory", "notes": "notes", "health": "health", "healthcare": "health"}
    if wl_name not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workload '{body.workload}'. Supported: 'inventory', 'notes', 'health'",
        )
    metrics = BenchmarkMetrics(
        workload=supported[wl_name],
        evaluation_status="illustrative_unvalidated",
        explanation=(
            "This development runner does not execute replica synchronization or a validated comparative "
            "experiment. Its former replica-B LWW proxy and hard-coded convergence values are unavailable. "
            "Domain-runner outputs are excluded from empirical results; use the separately documented stress "
            "benchmark for its limited, measured telemetry."
        ),
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
    if body.conflict_density not in (0.0, 0.05, 0.20, 0.50):
        raise HTTPException(
            status_code=400,
            detail="conflict_density must be 0, 0.05, 0.20, or 0.50.",
        )

    out_dir = str(DATA_DIR / "benchmarks") if body.export_artifacts else None
    cfg = StressBenchmarkConfig(
        num_operations=body.num_operations,
        conflict_density=body.conflict_density,
        seed=body.seed,
        trials=body.trials,
        output_dir=out_dir,
    )
    harness = StressHarness(cfg)
    result = harness.run_benchmark()

    # Cache latest stress result
    app_state.set_metrics("stress_latest", result.to_dict())

    return StressBenchmarkMetrics(**result.to_dict())


def get_artifact_dirs() -> list[Path]:
    """Return search directories for benchmark matrix artifacts."""
    return [
        Path("artifacts/benchmarks/historical-matrix-optimized-metric-corrected-20261013"),
        Path("artifacts/benchmarks/historical-matrix-optimized-original-20261013"),
        DATA_DIR / "benchmarks",
        Path("artifacts/benchmarks/historical-matrix-20261013"),
    ]


@router.get("/benchmark/artifacts", status_code=200)
def list_benchmark_artifacts() -> list[dict[str, Any]]:
    """List available benchmark JSON and CSV artifacts across known artifact folders."""
    dirs = get_artifact_dirs()
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
    from fastapi.responses import FileResponse

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    dirs = get_artifact_dirs()
    target_path = None
    for d in dirs:
        p = Path(d) / filename
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

