"""Exploratory benchmark for explicit operation-based additive increments.

This is a new experiment family. It does not rewrite or relabel the historical
SET-based stress artifacts. LWW is reported as an oracle-specific semantic
contrast only; paired timing deltas compare the increment engine with a direct
application-level additive merge using the same operation trace.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.fk_quarantine import connect_with_foreign_keys
from research.experiments.engine_evaluation import (
    _aggregate, _make_base, _percentile, _read_values, _source_snapshot,
    additive_oracle, evaluate_values, generate_trace, trace_digest,
)

SYSTEMS = ("application_sum", "engine_increment", "engine_lww")
ORDERS = (SYSTEMS, ("engine_increment", "engine_lww", "application_sum"),
          ("engine_lww", "application_sum", "engine_increment"))


def run_increment_engine(root: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    root.mkdir(parents=True)
    base = root / "base.sqlite"
    _make_base(base, len(operations))
    engine = CRDTSyncEngine(str(base), str(root / "replicas"))
    a = engine.create_replica("inc_a")
    b = engine.create_replica("inc_b")
    writes: list[float] = []
    for operation in operations:
        for path, replica_id, delta in ((a, "inc_a", operation["delta_a"]),
                                        *(([(b, "inc_b", operation["delta_b"])]
                                           if operation["is_conflict"] else []))):
            started = time.perf_counter()
            engine.apply_increment(path, replica_id, "bench_rows", operation["op_id"], "value", delta)
            writes.append((time.perf_counter() - started) * 1000)
    started = time.perf_counter()
    result = engine.sync_replicas(a, b, str(base), "inc_a", "inc_b",
                                  policies={"bench_rows": {"value": "SUM"}})
    sync_ms = (time.perf_counter() - started) * 1000
    receipt_count = 0
    for path in (a, b):
        with closing(sqlite3.connect(path)) as conn:
            receipt_count += int(conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0])
    return {"write_latency_ms": writes, "batch_sync_ms": sync_ms,
            "values_a": _read_values(a), "values_b": _read_values(b),
            "receipt_rows": receipt_count,
            "rejected_operations": result.rejected_operations,
            "total_conflicts": result.total_conflicts}


def run_application_sum(root: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    root.mkdir(parents=True)
    base = root / "base.sqlite"
    _make_base(base, len(operations))
    a, b = root / "a.sqlite", root / "b.sqlite"
    shutil.copy2(base, a)
    shutil.copy2(base, b)
    writes: list[float] = []
    for operation in operations:
        targets = [(a, operation["delta_a"])]
        if operation["is_conflict"]:
            targets.append((b, operation["delta_b"]))
        for path, delta in targets:
            started = time.perf_counter()
            with closing(connect_with_foreign_keys(str(path))) as conn:
                conn.execute("BEGIN IMMEDIATE")
                changed = conn.execute("UPDATE bench_rows SET value=value+? WHERE id=?",
                                       (delta, operation["op_id"]))
                if changed.rowcount != 1:
                    raise RuntimeError("application increment did not update exactly one row")
                conn.commit()
            writes.append((time.perf_counter() - started) * 1000)
    started = time.perf_counter()
    with closing(connect_with_foreign_keys(str(a))) as ca, closing(connect_with_foreign_keys(str(b))) as cb:
        ca.execute("BEGIN IMMEDIATE")
        cb.execute("BEGIN IMMEDIATE")
        va, vb = dict(ca.execute("SELECT id,value FROM bench_rows")), dict(cb.execute("SELECT id,value FROM bench_rows"))
        if va.keys() != vb.keys():
            raise RuntimeError("application baseline replicas have different row sets")
        for row_id in va:
            merged = 100 + (int(va[row_id]) - 100) + (int(vb[row_id]) - 100)
            if ca.execute("UPDATE bench_rows SET value=? WHERE id=?", (merged, row_id)).rowcount != 1:
                raise RuntimeError("application SUM write-back to A failed")
            if cb.execute("UPDATE bench_rows SET value=? WHERE id=?", (merged, row_id)).rowcount != 1:
                raise RuntimeError("application SUM write-back to B failed")
        ca.commit()
        cb.commit()
    return {"write_latency_ms": writes, "batch_sync_ms": (time.perf_counter() - started) * 1000,
            "values_a": _read_values(str(a)), "values_b": _read_values(str(b)),
            "receipt_rows": 0, "rejected_operations": [], "total_conflicts": None}


def run_configuration(n: int, density: float, seeds: list[int], output: Path) -> dict[str, Any]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("provide at least one unique independent seed")
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    trials = []
    for index, seed in enumerate(seeds):
        trial_started = datetime.now(timezone.utc).isoformat()
        ops = generate_trace(n, density, seed)
        digest = trace_digest(ops)
        trial = {"trial_index": index + 1, "trial_id": f"increment-{n}-{density:g}-{seed}",
                 "started_at_utc": trial_started, "seed": seed, "workload_digest": digest,
                 "num_operations": n, "conflict_density": density,
                 "conflict_count": sum(bool(op["is_conflict"]) for op in ops),
                 "execution_order": list(ORDERS[index % len(ORDERS)]),
                 "outcome": "SUCCESS", "systems": {}, "operations": ops}
        pair = output / f"trial_{index + 1}_seed_{seed}"
        pair.mkdir()
        try:
            for system in trial["execution_order"]:
                system_root = pair / system
                if system == "engine_increment":
                    result = run_increment_engine(system_root, ops)
                elif system == "application_sum":
                    result = run_application_sum(system_root, ops)
                else:
                    system_root.mkdir(parents=True)
                    base = system_root / "base.sqlite"
                    _make_base(base, n)
                    legacy_engine = CRDTSyncEngine(str(base), str(system_root / "replicas"))
                    ra, rb = legacy_engine.create_replica("lww_a"), legacy_engine.create_replica("lww_b")
                    lww_writes = []
                    for op in ops:
                        started = time.perf_counter()
                        legacy_engine.apply_change(ra, "lww_a", "bench_rows", op["op_id"], "value", op["value_a"])
                        lww_writes.append((time.perf_counter() - started) * 1000)
                        if op["is_conflict"]:
                            started = time.perf_counter()
                            legacy_engine.apply_change(rb, "lww_b", "bench_rows", op["op_id"], "value", op["value_b"])
                            lww_writes.append((time.perf_counter() - started) * 1000)
                    started = time.perf_counter()
                    sync = legacy_engine.sync_replicas(ra, rb, str(base), "lww_a", "lww_b",
                                                       policies={"bench_rows": {"value": "LWW"}})
                    result = {"write_latency_ms": lww_writes, "values_a": _read_values(ra),
                              "values_b": _read_values(rb), "batch_sync_ms": (time.perf_counter()-started)*1000,
                              "receipt_rows": None, "rejected_operations": sync.rejected_operations,
                              "total_conflicts": sync.total_conflicts}
                metrics = evaluate_values(ops, result["values_a"], result["values_b"])
                writes = result["write_latency_ms"]
                trial["systems"][system] = {
                    "metrics": metrics, "batch_sync_ms": result["batch_sync_ms"],
                    "receipt_rows": result["receipt_rows"], "total_conflicts": result["total_conflicts"],
                    "rejected_operation_count": len(result["rejected_operations"]),
                    "write_sample_count": len(writes), "write_p50_ms": _percentile(writes, .50),
                    "write_p95_ms": _percentile(writes, .95), "write_p99_ms": _percentile(writes, .99),
                    "observed_values_a": result["values_a"], "observed_values_b": result["values_b"],
                }
            increment_scr = trial["systems"]["engine_increment"]["metrics"]["oracle_specific_conflict_scr_pct"]
            if increment_scr is not None and increment_scr != 100.0:
                trial["outcome"] = "INVALID"
                trial["failure_reason"] = "INCREMENT engine did not match the declared additive oracle on all conflict rows"
        except Exception as exc:
            trial["outcome"] = "FAILED"
            trial["failure_reason"] = f"{type(exc).__name__}: {exc}"
        trial["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        trials.append(trial)
    successful = [item for item in trials if item["outcome"] == "SUCCESS"]
    paired = [item["systems"]["engine_increment"]["batch_sync_ms"]
              - item["systems"]["application_sum"]["batch_sync_ms"] for item in successful]
    source_snapshot = _source_snapshot(root)
    own_source = root / "research/experiments/increment_evaluation.py"
    source_snapshot.setdefault("relevant_file_sha256", {})["research/experiments/increment_evaluation.py"] = hashlib.sha256(own_source.read_bytes()).hexdigest()
    payload = {
        "schema_version": "operation-increment-exploratory-v1",
        "status": "exploratory_not_confirmatory",
        "configuration": {"num_operations": n, "conflict_density": density,
                           "seeds": seeds, "policy_assignments": {"engine_increment": "INCREMENT",
                           "application_sum": "direct additive operation merge", "engine_lww": "absolute SET + LWW semantic contrast"},
                           "workload_mode": "sequential tracked local writes followed by one batch synchronization"},
        "metric_definitions": {"scr": "Both replicas' conflict-row values compared with independently calculated base + delta_a + delta_b.",
                               "rvar": "Agreement on ordered bench_rows.value vectors only; not database convergence.",
                               "vra": "Not measured.",
                               "timing": "Write samples are per local mutation; batch_sync_ms excludes setup and writes.",
                               "comparison": "Paired sync timing compares engine INCREMENT with direct application additive merge only; the baseline does not provide equivalent operation receipts, conflict handling, quarantine, or checkpoint guarantees, so the timings are descriptive mechanism costs and do not establish a general performance advantage. LWW is a semantic contrast and excluded from paired timing claims."},
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "machine": platform.machine(), "processor": platform.processor() or None,
                        "cpu_count": os.cpu_count(), "sqlite_runtime_version": sqlite3.sqlite_version,
                        "journal_mode": "DELETE", "foreign_keys": "enabled for tracked/application connections",
                        "storage_medium": "not measured", "host_load": "not measured", "physical_memory": "not measured"},
        "source_snapshot": source_snapshot, "trial_count": len(trials),
        "successful_trial_count": len(successful), "failed_or_invalid_trial_count": len(trials)-len(successful),
        "paired_sync_delta_engine_increment_minus_application_sum_ms": {
            "sample_count": len(paired), "unit": "ms",
            "median": statistics.median(paired) if paired else None,
            "minimum": min(paired) if paired else None, "maximum": max(paired) if paired else None},
        "trials": trials,
    }
    stem = f"increment_evaluation_{n}_{int(density*100)}pct"
    json_path, csv_path = output / f"{stem}.json", output / f"{stem}.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["trial", "seed", "workload_digest", "outcome", "system", "execution_order",
                         "conflict_count", "scr_pct", "rvar_pct", "write_sample_count", "write_p95_ms",
                         "batch_sync_ms", "receipt_rows", "rejected_operations", "failure_reason"])
        for trial in trials:
            for name, result in trial.get("systems", {}).items():
                writer.writerow([trial["trial_index"], trial["seed"], trial["workload_digest"],
                                 trial["outcome"], name, ">".join(trial["execution_order"]),
                                 trial["conflict_count"], result["metrics"]["oracle_specific_conflict_scr_pct"],
                                 result["metrics"]["benchmark_row_value_agreement_pct"],
                                 result["write_sample_count"], result["write_p95_ms"],
                                 result["batch_sync_ms"], result["receipt_rows"],
                                 result["rejected_operation_count"], trial.get("failure_reason", "")])
    if len(successful) != len(trials):
        raise RuntimeError(f"experiment contains non-success outcomes; inspect retained records at {json_path}")
    return {"json": str(json_path), "csv": str(csv_path), "trials": len(trials),
            "paired_sync_delta_engine_increment_minus_application_sum_ms": payload["paired_sync_delta_engine_increment_minus_application_sum_ms"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operations", type=int, required=True)
    parser.add_argument("--density", type=float, required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    print(json.dumps(run_configuration(args.operations, args.density,
                                      list(range(args.seed, args.seed + args.trials)), args.output_dir), indent=2))


if __name__ == "__main__":
    main()
