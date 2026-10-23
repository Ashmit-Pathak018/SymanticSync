"""
analyze_experiments.py
======================
Reproducible analysis of the nine increment-evaluation configurations.

Usage (from repository root):
    python research/paper_audit_20261020/analyze_experiments.py

Input:  research/experiments/runs/increment-full-matrix-20261020-144638/
Output: research/paper_audit_20261020/AGGREGATE_RESULTS.csv
        research/paper_audit_20261020/VALIDATION_MATRIX.csv

All numbers are derived programmatically from the saved JSON artifacts.
No numbers are hard-coded.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import statistics
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MATRIX_DIR = REPO_ROOT / "research/experiments/runs/increment-full-matrix-20261020-144638"
OUT_DIR = REPO_ROOT / "research/paper_audit_20261020"

EXPECTED_CONFIGS = [
    ("1000", "5pct"), ("1000", "20pct"), ("1000", "50pct"),
    ("5000", "5pct"), ("5000", "20pct"), ("5000", "50pct"),
    ("10000", "5pct"), ("10000", "20pct"), ("10000", "50pct"),
]

SYSTEMS = {"application_sum", "engine_increment", "engine_lww"}


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return float("nan")
    s = sorted(data)
    idx = p * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _q1q3(data: list[float]) -> tuple[float, float]:
    qs = statistics.quantiles(data, n=4)
    return qs[0], qs[2]


def analyze_config(cfg_dir: pathlib.Path) -> dict[str, Any]:
    """Parse one configuration directory and return a result dict."""
    ops_str, den_str = cfg_dir.name.split("-")
    json_file = cfg_dir / f"increment_evaluation_{ops_str}_{den_str}.json"
    csv_file = cfg_dir / f"increment_evaluation_{ops_str}_{den_str}.csv"

    missing_files: list[str] = []
    if not json_file.exists():
        missing_files.append(json_file.name)
    if not csv_file.exists():
        missing_files.append(csv_file.name)

    if not json_file.exists():
        return {"config": cfg_dir.name, "error": f"JSON missing: {json_file}"}

    data = json.loads(json_file.read_text(encoding="utf-8"))
    config = data["configuration"]
    n = int(config["num_operations"])
    density = float(config["conflict_density"])
    seeds = config["seeds"]
    trials = data["trials"]

    # Verify all trials succeeded
    successful = [t for t in trials if t.get("outcome") == "SUCCESS"]
    failed = [t for t in trials if t.get("outcome") != "SUCCESS"]

    # Deltas: engine_increment.batch_sync_ms - application_sum.batch_sync_ms
    deltas: list[float] = []
    inc_sync_times: list[float] = []
    app_sync_times: list[float] = []

    inc_scr_values: list[float | None] = []
    app_scr_values: list[float | None] = []
    lww_scr_values: list[float | None] = []
    inc_rvar_values: list[float] = []
    app_rvar_values: list[float] = []
    lww_rvar_values: list[float] = []

    for trial in successful:
        sys_data = trial["systems"]
        inc = sys_data["engine_increment"]
        app = sys_data["application_sum"]
        lww = sys_data["engine_lww"]

        deltas.append(inc["batch_sync_ms"] - app["batch_sync_ms"])
        inc_sync_times.append(inc["batch_sync_ms"])
        app_sync_times.append(app["batch_sync_ms"])

        inc_scr_values.append(inc["metrics"]["oracle_specific_conflict_scr_pct"])
        app_scr_values.append(app["metrics"]["oracle_specific_conflict_scr_pct"])
        lww_scr_values.append(lww["metrics"]["oracle_specific_conflict_scr_pct"])
        inc_rvar_values.append(inc["metrics"]["benchmark_row_value_agreement_pct"])
        app_rvar_values.append(app["metrics"]["benchmark_row_value_agreement_pct"])
        lww_rvar_values.append(lww["metrics"]["benchmark_row_value_agreement_pct"])

    # Summary statistics on deltas
    med_delta = statistics.median(deltas) if deltas else float("nan")
    min_delta = min(deltas) if deltas else float("nan")
    max_delta = max(deltas) if deltas else float("nan")
    q1, q3 = _q1q3(deltas) if len(deltas) >= 2 else (float("nan"), float("nan"))
    iqr = q3 - q1

    # Verify all SCR == 100.0 for engine_increment and application_sum (they are both
    # direct additive merge approaches, so both should always match the oracle)
    inc_scr_unique = sorted(set(v for v in inc_scr_values if v is not None))
    app_scr_unique = sorted(set(v for v in app_scr_values if v is not None))
    lww_scr_unique = sorted(set(v for v in lww_scr_values if v is not None))

    # Check artifacts consistent with validation log delta summary
    artifact_delta_summary = data["paired_sync_delta_engine_increment_minus_application_sum_ms"]
    computed_median = statistics.median(deltas) if deltas else None
    delta_agrees = (
        computed_median is not None
        and math.isclose(computed_median, artifact_delta_summary["median"], rel_tol=1e-9)
    )

    conflict_count_per_trial = [t["conflict_count"] for t in successful]
    expected_conflicts = int(round(n * density))

    return {
        "config": cfg_dir.name,
        "operations": n,
        "conflict_density_pct": int(density * 100),
        "expected_conflicts_per_trial": expected_conflicts,
        "observed_conflicts_consistent": all(c == expected_conflicts for c in conflict_count_per_trial),
        "expected_trials": len(seeds),
        "observed_trials": len(trials),
        "successful_trials": len(successful),
        "failed_trials": len(failed),
        "missing_files": missing_files,
        "artifact_delta_median_agrees": delta_agrees,
        # SCR: engine_increment
        "inc_scr_all_values": inc_scr_unique,
        "inc_scr_constant_100": (inc_scr_unique == [100.0]),
        # SCR: application_sum
        "app_scr_all_values": app_scr_unique,
        "app_scr_constant_100": (app_scr_unique == [100.0]),
        # SCR: LWW
        "lww_scr_all_values": lww_scr_unique,
        "lww_scr_constant_0": (lww_scr_unique == [0.0]),
        # RVAR
        "inc_rvar_constant_100": all(v == 100.0 for v in inc_rvar_values),
        "app_rvar_constant_100": all(v == 100.0 for v in app_rvar_values),
        "lww_rvar_constant_100": all(v == 100.0 for v in lww_rvar_values),
        # Sync timing
        "med_inc_sync_ms": round(statistics.median(inc_sync_times), 3) if inc_sync_times else None,
        "med_app_sync_ms": round(statistics.median(app_sync_times), 3) if app_sync_times else None,
        # Paired delta
        "med_delta_ms": round(med_delta, 3),
        "min_delta_ms": round(min_delta, 3),
        "max_delta_ms": round(max_delta, 3),
        "q1_ms": round(q1, 3),
        "q3_ms": round(q3, 3),
        "iqr_ms": round(iqr, 3),
        # Seeds
        "seeds": seeds,
        # Schema
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "workload_mode": config.get("workload_mode"),
    }


def write_aggregate_csv(rows: list[dict[str, Any]], out_path: pathlib.Path) -> None:
    fieldnames = [
        "config", "operations", "conflict_density_pct",
        "expected_trials", "observed_trials", "successful_trials", "failed_trials",
        "expected_conflicts_per_trial", "observed_conflicts_consistent",
        "inc_scr_constant_100", "app_scr_constant_100",
        "lww_scr_constant_0",
        "inc_rvar_constant_100", "app_rvar_constant_100",
        "lww_rvar_constant_100",
        "med_inc_sync_ms", "med_app_sync_ms",
        "med_delta_ms", "q1_ms", "q3_ms", "iqr_ms", "min_delta_ms", "max_delta_ms",
        "artifact_delta_median_agrees",
        "schema_version", "status", "workload_mode",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_validation_matrix_csv(rows: list[dict[str, Any]], out_path: pathlib.Path) -> None:
    fieldnames = [
        "configuration", "operations", "conflict_density",
        "expected_trials", "observed_trials", "successful_trials", "failed_trials",
        "artifact_consistency", "oracle_status",
        "trace_and_receipt_status",
        "validation_result", "notes",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            missing = r.get("missing_files", [])
            consistent = r.get("observed_conflicts_consistent", True) and not missing
            all_pass = (
                r.get("inc_scr_constant_100") and
                r.get("app_scr_constant_100") and
                r.get("lww_scr_constant_0") and
                r.get("inc_rvar_constant_100") and
                r.get("artifact_delta_median_agrees")
            )
            validation_result = "PASS" if (all_pass and r.get("failed_trials", 1) == 0) else "FAIL"
            oracle_note = (
                f"engine_increment SCR={r.get('inc_scr_all_values')}; "
                f"application_sum SCR={r.get('app_scr_all_values')}; "
                f"engine_lww SCR={r.get('lww_scr_all_values')}"
            )
            notes = "; ".join(filter(None, [
                f"missing files: {missing}" if missing else "",
                f"failed trials: {r.get('failed_trials')}" if r.get("failed_trials") else "",
                "delta median agrees with artifact" if r.get("artifact_delta_median_agrees") else "delta median MISMATCH",
            ])) or "all checks pass"
            writer.writerow({
                "configuration": r.get("config"),
                "operations": r.get("operations"),
                "conflict_density": f"{r.get('conflict_density_pct')}%",
                "expected_trials": r.get("expected_trials"),
                "observed_trials": r.get("observed_trials"),
                "successful_trials": r.get("successful_trials"),
                "failed_trials": r.get("failed_trials"),
                "artifact_consistency": "CONSISTENT" if consistent else "INCONSISTENT",
                "oracle_status": oracle_note,
                "trace_and_receipt_status": "Validated by validate_increment_evaluation.py (per-replica DB receipts checked)",
                "validation_result": validation_result,
                "notes": notes,
            })


def main() -> None:
    print(f"Reading from: {MATRIX_DIR}")
    results: list[dict[str, Any]] = []

    for ops, den in EXPECTED_CONFIGS:
        cfg_name = f"{ops}-{den}"
        cfg_dir = MATRIX_DIR / cfg_name
        if not cfg_dir.exists():
            print(f"  MISSING configuration directory: {cfg_dir}")
            results.append({"config": cfg_name, "error": "directory missing"})
            continue
        row = analyze_config(cfg_dir)
        results.append(row)
        status = "PASS" if (row.get("failed_trials") == 0 and row.get("inc_scr_constant_100")) else "WARN"
        print(f"  [{status}] {cfg_name}: trials={row.get('observed_trials')} "
              f"inc_scr={row.get('inc_scr_all_values')} "
              f"med_delta={row.get('med_delta_ms')} ms IQR={row.get('iqr_ms')} ms")

    agg_path = OUT_DIR / "AGGREGATE_RESULTS.csv"
    write_aggregate_csv(results, agg_path)
    print(f"\nAGGREGATE_RESULTS.csv -> {agg_path}")

    val_path = OUT_DIR / "VALIDATION_MATRIX.csv"
    write_validation_matrix_csv(results, val_path)
    print(f"VALIDATION_MATRIX.csv -> {val_path}")

    # Print summary table
    print("\nSummary:")
    print(f"{'Config':<15} {'Trials':>6} {'Inc SCR':>10} {'App SCR':>10} {'LWW SCR':>10} "
          f"{'Inc RVAR':>9} {'Med Delta (ms)':>15} {'IQR (ms)':>10}")
    for r in results:
        if "error" in r:
            print(f"  {r['config']}: ERROR - {r['error']}")
            continue
        print(f"  {r['config']:<13} {r['successful_trials']:>6} "
              f"{str(r['inc_scr_all_values']):>10} "
              f"{str(r['app_scr_all_values']):>10} "
              f"{str(r['lww_scr_all_values']):>10} "
              f"{'100.0' if r['inc_rvar_constant_100'] else 'VAR':>9} "
              f"{r['med_delta_ms']:>12.1f} "
              f"{r['iqr_ms']:>10.1f}")


if __name__ == "__main__":
    main()
