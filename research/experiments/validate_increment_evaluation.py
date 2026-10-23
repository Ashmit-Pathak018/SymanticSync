"""Validate saved explicit-INCREMENT JSON/CSV records without running trials."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
from typing import Any

SYSTEMS = {"application_sum", "engine_increment", "engine_lww"}


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _numeric(actual: Any, expected: float, message: str) -> None:
    _check(isinstance(actual, (int, float)) and math.isclose(
        float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-9), message)


def validate(json_path: Path) -> dict[str, Any]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    _check(data.get("schema_version") == "operation-increment-exploratory-v1", "unsupported schema")
    _check(data.get("status") == "exploratory_not_confirmatory", "run must remain exploratory")
    config = data["configuration"]
    n, density = int(config["num_operations"]), float(config["conflict_density"])
    trials = data.get("trials")
    _check(isinstance(trials, list) and trials, "trial records missing")
    _check(len(trials) == data["trial_count"] == len(config["seeds"]), "trial/seed count mismatch")
    _check(data["successful_trial_count"] == len(trials)
           and data["failed_or_invalid_trial_count"] == 0, "run contains failed or invalid trials")
    source_hash = data.get("source_snapshot", {}).get("relevant_file_sha256", {}).get(
        "research/experiments/increment_evaluation.py")
    _check(isinstance(source_hash, str) and len(source_hash) == 64, "runner hash missing")
    env = data.get("environment", {})
    for key in ("python", "platform", "sqlite_runtime_version", "journal_mode", "foreign_keys"):
        _check(env.get(key) not in (None, ""), f"environment field missing: {key}")

    deltas: list[float] = []
    csv_expectations: dict[tuple[int, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    seen_seeds: set[int] = set()
    seen_digests: set[str] = set()
    for index, trial in enumerate(trials, start=1):
        _check(trial.get("outcome") == "SUCCESS", f"trial {index} did not succeed")
        seed = int(trial["seed"])
        _check(seed == int(config["seeds"][index - 1]) and seed not in seen_seeds,
               "seed order/uniqueness mismatch")
        seen_seeds.add(seed)
        _check(trial["num_operations"] == n and math.isclose(trial["conflict_density"], density),
               f"trial {index} configuration mismatch")
        operations = trial.get("operations")
        _check(isinstance(operations, list) and len(operations) == n,
               f"trial {index} operation list mismatch")
        by_id = {int(op["op_id"]): op for op in operations}
        _check(len(by_id) == n and set(by_id) == set(range(1, n + 1)),
               f"trial {index} operation IDs invalid")
        conflicts = sum(bool(op["is_conflict"]) for op in operations)
        _check(conflicts == int(round(n * density)) == int(trial["conflict_count"]),
               f"trial {index} conflict count mismatch")
        canonical = json.dumps(operations, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        _check(trial.get("workload_digest") == digest and digest not in seen_digests,
               f"trial {index} workload digest invalid or duplicated")
        seen_digests.add(digest)
        systems = trial.get("systems", {})
        _check(set(systems) == SYSTEMS, f"trial {index} system set mismatch")
        order = trial.get("execution_order")
        _check(isinstance(order, list) and len(order) == len(SYSTEMS) and set(order) == SYSTEMS,
               f"trial {index} execution order invalid")

        for name, result in systems.items():
            values_a, values_b = result["observed_values_a"], result["observed_values_b"]
            _check(len(values_a) == len(values_b) == n, f"trial {index} {name} row vector mismatch")
            expected = {
                op_id: int(op["base"]) + int(op["delta_a"])
                + (int(op["delta_b"]) if op["is_conflict"] else 0)
                for op_id, op in by_id.items()
            }
            matches = sum(values[op_id - 1] == expected[op_id]
                          for op_id, op in by_id.items() if op["is_conflict"]
                          for values in (values_a, values_b))
            scr = 100.0 * matches / (2 * conflicts) if conflicts else None
            rvar = 100.0 * sum(a == b for a, b in zip(values_a, values_b)) / n
            metrics = result["metrics"]
            _check(metrics["conflict_rows"] == conflicts
                   and metrics["oracle_denominator"] == 2 * conflicts,
                   f"trial {index} {name} SCR denominator mismatch")
            if scr is None:
                _check(metrics["oracle_specific_conflict_scr_pct"] is None,
                       "zero-conflict SCR must be null")
            else:
                _numeric(metrics["oracle_specific_conflict_scr_pct"], scr,
                         f"trial {index} {name} SCR mismatch")
            _numeric(metrics["benchmark_row_value_agreement_pct"], rvar,
                     f"trial {index} {name} RVAR mismatch")
            _check(int(result["write_sample_count"]) > 0, f"trial {index} {name} write samples missing")
            for key in ("batch_sync_ms", "write_p50_ms", "write_p95_ms", "write_p99_ms"):
                value = result.get(key)
                _check(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0,
                       f"trial {index} {name} invalid {key}")
            csv_expectations[(index, name)] = (trial, result)

        expected_receipts = n + conflicts
        replica_dir = (json_path.parent / f"trial_{index}_seed_{seed}"
                       / "engine_increment" / "replicas")
        for replica in ("inc_a", "inc_b"):
            db = replica_dir / f"{replica}.db"
            _check(db.is_file(), f"trial {index} missing {replica} database")
            with sqlite3.connect(db) as conn:
                _check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                       f"trial {index} {replica} SQLite integrity failed")
                ids = [str(row[0]) for row in conn.execute(
                    "SELECT origin_id FROM _ss_change_log WHERE op_type='INCREMENT'")]
            _check(len(ids) == expected_receipts and len(set(ids)) == expected_receipts,
                   f"trial {index} {replica} increment receipt set invalid")
        deltas.append(systems["engine_increment"]["batch_sync_ms"]
                      - systems["application_sum"]["batch_sync_ms"])

    summary = data["paired_sync_delta_engine_increment_minus_application_sum_ms"]
    _check(summary["sample_count"] == len(deltas) and summary["unit"] == "ms",
           "paired summary metadata mismatch")
    _numeric(summary["median"], statistics.median(deltas), "paired median mismatch")
    _numeric(summary["minimum"], min(deltas), "paired minimum mismatch")
    _numeric(summary["maximum"], max(deltas), "paired maximum mismatch")

    csv_path = json_path.with_suffix(".csv")
    _check(csv_path.is_file(), "paired CSV missing")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    _check(len(csv_rows) == len(trials) * len(SYSTEMS), "CSV row count mismatch")
    indexed = {(int(row["trial"]), row["system"]): row for row in csv_rows}
    _check(len(indexed) == len(csv_rows), "duplicate CSV trial/system row")
    for (index, name), (trial, result) in csv_expectations.items():
        row = indexed.get((index, name))
        _check(row is not None and row["workload_digest"] == trial["workload_digest"],
               "CSV trial/digest mismatch")
        _check(row["execution_order"] == ">".join(trial["execution_order"]),
               "CSV execution order mismatch")
        _check(row["outcome"] == trial["outcome"]
               and int(row["conflict_count"]) == trial["conflict_count"],
               "CSV trial metadata mismatch")
        for csv_key, metric_key in (
            ("scr_pct", "oracle_specific_conflict_scr_pct"),
            ("rvar_pct", "benchmark_row_value_agreement_pct"),
        ):
            value = result["metrics"][metric_key]
            if value is None:
                _check(row[csv_key] == "", f"CSV {csv_key} must be blank for null")
            else:
                _numeric(float(row[csv_key]), value, f"CSV {csv_key} mismatch")
        _numeric(float(row["batch_sync_ms"]), result["batch_sync_ms"], "CSV sync time mismatch")
        _check(int(row["write_sample_count"]) == result["write_sample_count"],
               "CSV write sample count mismatch")
    return {"trial_count": len(trials), "trial_sync_deltas_ms": deltas,
            "median_delta_ms": statistics.median(deltas)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()
    result = validate(args.json_path)
    print("VALIDATION PASSED: JSON/CSV, oracle, traces, and per-replica receipts agree")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
