"""Independent-seed, engine-level pilot for SemanticSync's integer SUM workload.

The application baseline implements the same scalar additive rule using direct
SQLite writes. It deliberately does not provide SemanticSync's operation log,
replay receipts, conflict records, FK quarantine, or checkpoint guarantees, so
timing differences are a narrow mechanism comparison only.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
import hashlib
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.fk_quarantine import connect_with_foreign_keys


SYSTEMS = ("application_sum", "engine_sum", "engine_lww")
SOURCE_FILES = (
    "backend/engine/crdt_sync.py",
    "backend/engine/conflict_detector.py",
    "backend/engine/semantic_resolver.py",
    "backend/engine/fk_quarantine.py",
    "research/experiments/engine_evaluation.py",
)
ORDER_CYCLE = (
    SYSTEMS,
    ("engine_sum", "engine_lww", "application_sum"),
    ("engine_lww", "application_sum", "engine_sum"),
)


def generate_trace(num_operations: int, conflict_density: float, seed: int) -> list[dict[str, Any]]:
    if num_operations <= 0:
        raise ValueError("num_operations must be positive")
    if not 0 <= conflict_density <= 1:
        raise ValueError("conflict_density must be between zero and one")
    rng = random.Random(seed)
    conflict_count = int(round(num_operations * conflict_density))
    operations = []
    for index in range(num_operations):
        is_conflict = index < conflict_count
        delta_a = rng.randint(1, 50)
        delta_b = rng.randint(1, 50) if is_conflict else 0
        operations.append({
            "op_id": index + 1,
            "is_conflict": is_conflict,
            "base": 100,
            "delta_a": delta_a,
            "delta_b": delta_b,
            "value_a": 100 + delta_a,
            "value_b": 100 + delta_b,
        })
    rng.shuffle(operations)
    return operations


def trace_digest(operations: list[dict[str, Any]]) -> str:
    payload = json.dumps(operations, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_snapshot(repo_root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root, check=True, capture_output=True, text=True,
        ).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    hashes = {}
    for relative in SOURCE_FILES:
        source_path = repo_root / relative
        if source_path.is_file():
            hashes[relative] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return {"git_revision": revision, "worktree_dirty": dirty,
            "relevant_file_sha256": hashes}


def additive_oracle(operations: list[dict[str, Any]]) -> dict[int, int]:
    """Independent expected values, not imported from the production harness."""
    expected: dict[int, int] = {}
    for operation in operations:
        contributions = operation["delta_a"]
        if operation["is_conflict"]:
            contributions += operation["delta_b"]
        expected[int(operation["op_id"])] = int(operation["base"] + contributions)
    return expected


def evaluate_values(
    operations: list[dict[str, Any]], values_a: list[int], values_b: list[int],
) -> dict[str, float | int | None]:
    ordered_ops = sorted(operations, key=lambda item: int(item["op_id"]))
    if len(values_a) != len(ordered_ops) or len(values_b) != len(ordered_ops):
        raise ValueError("Observed replica values do not match workload row count")
    expected = additive_oracle(operations)
    conflicts = [index for index, op in enumerate(ordered_ops) if op["is_conflict"]]
    scr = None
    if conflicts:
        matches = sum(values[index] == expected[int(ordered_ops[index]["op_id"])]
                      for index in conflicts for values in (values_a, values_b))
        scr = matches / (2 * len(conflicts)) * 100.0
    agreement = (sum(a == b for a, b in zip(values_a, values_b)) / len(ordered_ops) * 100.0)
    return {"oracle_specific_conflict_scr_pct": scr,
            "benchmark_row_value_agreement_pct": agreement,
            "conflict_rows": len(conflicts),
            "oracle_denominator": 2 * len(conflicts)}


def _make_base(path: Path, row_count: int) -> None:
    with closing(sqlite3.connect(path)) as conn:
        with conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            conn.executemany("INSERT INTO bench_rows(id,value) VALUES (?,100)",
                             ((index,) for index in range(1, row_count + 1)))


def _read_values(path: str) -> list[int]:
    with closing(sqlite3.connect(path)) as conn:
        return [int(row[0]) for row in conn.execute("SELECT value FROM bench_rows ORDER BY id")]


def _run_engine(root: Path, operations: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    root.mkdir(parents=True)
    base = root / "base.sqlite"
    _make_base(base, len(operations))
    engine = CRDTSyncEngine(base_db_path=str(base), data_dir=str(root / "replicas"))
    replica_a = engine.create_replica("research_a")
    replica_b = engine.create_replica("research_b")
    write_ms: list[float] = []
    for operation in operations:
        started = time.perf_counter()
        engine.apply_change(replica_a, "research_a", "bench_rows", operation["op_id"],
                            "value", operation["value_a"])
        write_ms.append((time.perf_counter() - started) * 1000)
        if operation["is_conflict"]:
            started = time.perf_counter()
            engine.apply_change(replica_b, "research_b", "bench_rows", operation["op_id"],
                                "value", operation["value_b"])
            write_ms.append((time.perf_counter() - started) * 1000)
    started = time.perf_counter()
    sync_result = engine.sync_replicas(
        replica_a, replica_b, str(base), "research_a", "research_b",
        policies={"bench_rows": {"value": policy}},
    )
    sync_ms = (time.perf_counter() - started) * 1000
    values_a, values_b = _read_values(replica_a), _read_values(replica_b)
    receipts = 0
    for path in (replica_a, replica_b):
        with closing(sqlite3.connect(path)) as conn:
            receipts += int(conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0])
    return {"write_latency_ms": write_ms, "batch_sync_ms": sync_ms,
            "values_a": values_a, "values_b": values_b, "receipt_rows": receipts,
            "sync_result": {"total_conflicts": sync_result.total_conflicts,
                "auto_resolved": sync_result.auto_resolved,
                "flagged_for_review": sync_result.flagged_for_review,
                "skipped_tables": sync_result.skipped_tables,
                "rejected_operation_count": len(sync_result.rejected_operations)}}


def _run_application_sum(root: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    root.mkdir(parents=True)
    base = root / "base.sqlite"
    _make_base(base, len(operations))
    path_a, path_b = root / "replica_a.sqlite", root / "replica_b.sqlite"
    shutil.copy2(base, path_a)
    shutil.copy2(base, path_b)
    write_ms: list[float] = []
    for operation in operations:
        targets = [(path_a, operation["value_a"])]
        if operation["is_conflict"]:
            targets.append((path_b, operation["value_b"]))
        for path, value in targets:
            started = time.perf_counter()
            with closing(connect_with_foreign_keys(str(path))) as conn:
                conn.execute("BEGIN IMMEDIATE")
                changed = conn.execute("UPDATE bench_rows SET value=? WHERE id=?",
                                       (value, operation["op_id"]))
                if changed.rowcount != 1:
                    raise RuntimeError("application baseline write did not update one row")
                conn.commit()
            write_ms.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    # This is a narrow direct-SQL merge; it has no durable operation protocol.
    with closing(connect_with_foreign_keys(str(path_a))) as conn_a, \
            closing(connect_with_foreign_keys(str(path_b))) as conn_b:
        conn_a.execute("BEGIN IMMEDIATE")
        conn_b.execute("BEGIN IMMEDIATE")
        a_rows = dict(conn_a.execute("SELECT id,value FROM bench_rows"))
        b_rows = dict(conn_b.execute("SELECT id,value FROM bench_rows"))
        if set(a_rows) != set(b_rows):
            raise RuntimeError("application baseline replica row sets differ")
        merged = {row_id: 100 + (int(a_rows[row_id]) - 100) + (int(b_rows[row_id]) - 100)
                  for row_id in a_rows}
        for row_id, value in merged.items():
            if conn_a.execute("UPDATE bench_rows SET value=? WHERE id=?", (value, row_id)).rowcount != 1:
                raise RuntimeError("application baseline write-back to A did not update one row")
            if conn_b.execute("UPDATE bench_rows SET value=? WHERE id=?", (value, row_id)).rowcount != 1:
                raise RuntimeError("application baseline write-back to B did not update one row")
        conn_a.commit()
        conn_b.commit()
    sync_ms = (time.perf_counter() - started) * 1000
    return {"write_latency_ms": write_ms, "batch_sync_ms": sync_ms,
            "values_a": _read_values(str(path_a)), "values_b": _read_values(str(path_b)),
            "receipt_rows": 0,
            "sync_result": {"status": "completed", "rejected_operation_count": 0}}


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def _trial_summary(run: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = evaluate_values(operations, run["values_a"], run["values_b"])
    writes = run["write_latency_ms"]
    return {"metrics": metrics,
            "tracked_or_direct_write_sample_count": len(writes),
            "write_p50_ms": _percentile(writes, .50),
            "write_p95_ms": _percentile(writes, .95),
            "write_p99_ms": _percentile(writes, .99),
            "batch_sync_ms": run["batch_sync_ms"],
            "receipt_rows": run["receipt_rows"],
            "sync_result": run["sync_result"]}


def _aggregate(values: list[float], unit: str) -> dict[str, Any]:
    return {"sample_count": len(values), "unit": unit,
            "median": statistics.median(values) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None}


def run_configuration(
    num_operations: int, conflict_density: float, seeds: list[int], output_dir: Path,
) -> dict[str, Any]:
    if not seeds:
        raise ValueError("at least one independent seed is required")
    repo_root = Path(__file__).resolve().parents[2]
    source_snapshot = _source_snapshot(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    trials: list[dict[str, Any]] = []
    for trial_index, seed in enumerate(seeds):
        operations = generate_trace(num_operations, conflict_density, seed)
        digest = trace_digest(operations)
        order = list(ORDER_CYCLE[trial_index % len(ORDER_CYCLE)])
        pair_root = output_dir / f"trial_{trial_index + 1}_seed_{seed}"
        if pair_root.exists():
            raise FileExistsError(f"trial directory already exists; use a new output directory: {pair_root}")
        pair_root.mkdir(parents=True)
        trial: dict[str, Any] = {"trial_index": trial_index + 1, "seed": seed,
            "workload_digest": digest, "num_operations": num_operations,
            "conflict_density": conflict_density,
            "conflict_count": sum(bool(op["is_conflict"]) for op in operations),
            "execution_order": order, "outcome": "SUCCESS", "systems": {},
            "database_directory": str(pair_root)}
        try:
            for system in order:
                run_root = pair_root / system
                if system == "application_sum":
                    run = _run_application_sum(run_root, operations)
                else:
                    policy = "SUM" if system == "engine_sum" else "LWW"
                    run = _run_engine(run_root, operations, policy)
                trial["systems"][system] = _trial_summary(run, operations)
                # Keep the actual observed rows in raw records for independent re-scoring.
                trial["systems"][system]["observed_values_a"] = run["values_a"]
                trial["systems"][system]["observed_values_b"] = run["values_b"]
            if not len({trial["systems"][system]["metrics"]["conflict_rows"]
                        for system in SYSTEMS}) == 1:
                raise RuntimeError("systems evaluated different conflict-row counts")
        except Exception as exc:
            trial["outcome"] = "FAILED"
            trial["failure_reason"] = f"{type(exc).__name__}: {exc}"
        trial["operations"] = operations
        trials.append(trial)

    summaries: dict[str, Any] = {}
    successful = [trial for trial in trials if trial["outcome"] == "SUCCESS"]
    for system in SYSTEMS:
        runs = [trial["systems"][system] for trial in successful]
        summaries[system] = {
            "batch_sync_ms": _aggregate([float(run["batch_sync_ms"]) for run in runs], "ms"),
            "write_p50_ms": _aggregate([float(run["write_p50_ms"]) for run in runs], "ms"),
            "write_p95_ms": _aggregate([float(run["write_p95_ms"]) for run in runs], "ms"),
            "write_p99_ms": _aggregate([float(run["write_p99_ms"]) for run in runs], "ms"),
            "oracle_specific_conflict_scr_pct": _aggregate([
                float(run["metrics"]["oracle_specific_conflict_scr_pct"])
                for run in runs if run["metrics"]["oracle_specific_conflict_scr_pct"] is not None], "percent"),
            "benchmark_row_value_agreement_pct": _aggregate([
                float(run["metrics"]["benchmark_row_value_agreement_pct"]) for run in runs], "percent"),
        }
    paired = {
        "engine_sum_minus_application_sum_batch_sync_ms": _aggregate([
            float(trial["systems"]["engine_sum"]["batch_sync_ms"])
            - float(trial["systems"]["application_sum"]["batch_sync_ms"])
            for trial in successful], "ms"),
        "engine_lww_minus_application_sum_batch_sync_ms": _aggregate([
            float(trial["systems"]["engine_lww"]["batch_sync_ms"])
            - float(trial["systems"]["application_sum"]["batch_sync_ms"])
            for trial in successful], "ms"),
    }
    environment = {"python": sys.version, "platform": platform.platform(),
        "machine": platform.machine(), "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(), "sqlite_runtime_version": sqlite3.sqlite_version,
        "journal_mode": "DELETE", "foreign_keys": "enabled for each connection",
        "host_load": "not measured", "storage_medium": "not measured",
        "physical_memory": "not measured"}
    payload = {"schema_version": "research-engine-evaluation-v1",
        "metric_definitions": {
            "oracle_specific_conflict_scr_pct": "Conflict rows only, both replicas scored against base + generated deltas; LWW is not semantically equivalent to this additive oracle.",
            "benchmark_row_value_agreement_pct": "Agreement over ordered bench_rows.value vectors only; not full-database convergence.",
            "vra": "Not measured.",
            "application_sum_baseline": "Same scalar additive rule implemented with direct SQLite writes; omits engine operation identity, receipts, conflict persistence, quarantine, and checkpoint guarantees.",
            "batch_sync_ms": "Wall time around engine sync_replicas or the direct-SQL application merge; initialization and local writes excluded."},
        "configuration": {"num_operations": num_operations,
            "conflict_density": conflict_density,
            "seed_list": seeds, "independent_seed_count": len(seeds),
            "policy_assignments": {"engine_sum": "SUM", "engine_lww": "LWW",
                                   "application_sum": "base-relative additive merge"},
            "workload_mode": "sequential local writes followed by one batch merge/sync"},
        "environment": environment, "source_snapshot": source_snapshot,
        "trial_count": len(trials),
        "successful_trial_count": len(successful),
        "failed_trial_count": len(trials) - len(successful),
        "trial_summaries": summaries, "paired_deltas": paired,
        "trials": trials}
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"engine_evaluation_{num_operations}_{int(conflict_density * 100)}pct"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["trial", "seed", "workload_digest", "outcome", "system",
                         "execution_order", "conflict_count", "scr_pct",
                         "row_value_agreement_pct", "write_p50_ms", "write_p95_ms",
                         "write_p99_ms", "batch_sync_ms", "receipt_rows", "failure_reason"])
        for trial in trials:
            for system in SYSTEMS:
                result = trial.get("systems", {}).get(system, {})
                metrics = result.get("metrics", {})
                writer.writerow([trial["trial_index"], trial["seed"],
                    trial["workload_digest"], trial["outcome"], system,
                    ">".join(trial["execution_order"]), trial["conflict_count"],
                    metrics.get("oracle_specific_conflict_scr_pct"),
                    metrics.get("benchmark_row_value_agreement_pct"),
                    result.get("write_p50_ms"), result.get("write_p95_ms"),
                    result.get("write_p99_ms"), result.get("batch_sync_ms"),
                    result.get("receipt_rows"), trial.get("failure_reason", "")])
    if len(successful) != len(trials):
        raise RuntimeError(f"one or more trials failed; records retained in {json_path}")
    return {"json": str(json_path), "csv": str(csv_path),
            "successful_trials": len(successful), "trial_count": len(trials),
            "trial_summaries": summaries, "paired_deltas": paired}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operations", type=int, required=True)
    parser.add_argument("--density", type=float, required=True)
    parser.add_argument("--trials", type=int, default=3,
                        help="number of distinct paired workload seeds (default: 3 pilot trials)")
    parser.add_argument("--seed", type=int, default=20261020,
                        help="first seed; following trials use successive integer seeds")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    result = run_configuration(args.operations, args.density,
                               list(range(args.seed, args.seed + args.trials)), args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
