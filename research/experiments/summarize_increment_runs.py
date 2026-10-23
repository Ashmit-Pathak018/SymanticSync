"""Summarize saved explicit-INCREMENT run records without rerunning trials."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any

from research.experiments.validate_increment_evaluation import validate

SYSTEMS = ("application_sum", "engine_increment", "engine_lww")


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("cannot summarize an empty or non-finite sample")
    quartiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else [values[0]] * 3
    return {
        "sample_count": len(values),
        "unit": "ms",
        "mean": statistics.mean(values),
        "sample_standard_deviation": statistics.stdev(values) if len(values) > 1 else None,
        "median": statistics.median(values),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "minimum": min(values),
        "maximum": max(values),
    }


def summarize(input_paths: list[Path], output_dir: Path) -> tuple[Path, Path]:
    if not input_paths:
        raise ValueError("at least one run record is required for a summary")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    runs: list[tuple[Path, dict[str, Any]]] = []
    for path in input_paths:
        validate(path)
        runs.append((path, json.loads(path.read_text(encoding="utf-8"))))

    first = runs[0][1]
    config = first["configuration"]
    comparable_config = {key: value for key, value in config.items() if key != "seeds"}
    provenance = (first["source_snapshot"], first["environment"], first["metric_definitions"])
    trials: list[dict[str, Any]] = []
    seen_seeds: set[int] = set()
    seen_digests: set[str] = set()
    for path, run in runs:
        current_config = run["configuration"]
        if ({key: value for key, value in current_config.items() if key != "seeds"}
                != comparable_config):
            raise ValueError(f"incompatible workload or policy configuration: {path}")
        if (run["source_snapshot"], run["environment"], run["metric_definitions"]) != provenance:
            raise ValueError(f"incompatible source, environment, or metric definitions: {path}")
        for trial in run["trials"]:
            seed, digest = int(trial["seed"]), str(trial["workload_digest"])
            if seed in seen_seeds or digest in seen_digests:
                raise ValueError(f"duplicate seed or workload digest across runs: {path}")
            seen_seeds.add(seed)
            seen_digests.add(digest)
            trials.append({"source_json": str(path), **trial})

    if len(seen_seeds) != len(trials):
        raise ValueError("pooled seed count does not match trial count")
    paired = [t["systems"]["engine_increment"]["batch_sync_ms"]
              - t["systems"]["application_sum"]["batch_sync_ms"] for t in trials]
    systems: dict[str, Any] = {}
    for name in SYSTEMS:
        sync_values = [float(t["systems"][name]["batch_sync_ms"]) for t in trials]
        write_p95 = [float(t["systems"][name]["write_p95_ms"]) for t in trials]
        scr_values = [t["systems"][name]["metrics"]["oracle_specific_conflict_scr_pct"]
                      for t in trials]
        rvar_values = [float(t["systems"][name]["metrics"]["benchmark_row_value_agreement_pct"])
                       for t in trials]
        systems[name] = {
            "batch_sync": _distribution(sync_values),
            "per_trial_write_p95": _distribution(write_p95),
            "scr_values_pct": scr_values,
            "rvar_values_pct": rvar_values,
        }

    payload = {
        "schema_version": ("increment-run-summary-v1" if len(runs) == 1
                           else "increment-pilot-pooled-summary-v1"),
        "status": "exploratory_not_confirmatory",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": (
            ("Descriptive statistics for trials in one validated run. " if len(runs) == 1 else
             "Descriptive pooling of independent seeds with identical recorded source hashes, "
             "environment, workload configuration, and metric definitions. ")
            + "The direct-SQL SUM path lacks equivalent system guarantees; paired deltas are not "
            "end-to-end overhead or evidence of a general performance advantage. LWW is an "
            "additive-oracle semantic contrast. No statistical significance or general "
            "convergence is claimed."
        ),
        "configuration": comparable_config,
        "source_snapshot": first["source_snapshot"],
        "environment": first["environment"],
        "metric_definitions": first["metric_definitions"],
        "source_json_files": [str(path) for path, _ in runs],
        "trial_count": len(trials),
        "unique_seed_count": len(seen_seeds),
        "unique_workload_digest_count": len(seen_digests),
        "execution_order_counts": {
            ">".join(order): sum(tuple(t["execution_order"]) == order for t in trials)
            for order in sorted({tuple(t["execution_order"]) for t in trials})
        },
        "systems": systems,
        "paired_sync_delta_engine_increment_minus_application_sum": _distribution(paired),
        "trials": [{
            "trial_id": t["trial_id"], "seed": t["seed"],
            "workload_digest": t["workload_digest"], "outcome": t["outcome"],
            "execution_order": t["execution_order"], "source_json": t["source_json"],
            "systems": {name: {
                "batch_sync_ms": t["systems"][name]["batch_sync_ms"],
                "scr_pct": t["systems"][name]["metrics"]["oracle_specific_conflict_scr_pct"],
                "rvar_pct": t["systems"][name]["metrics"]["benchmark_row_value_agreement_pct"],
            } for name in SYSTEMS},
            "paired_delta_ms": t["systems"]["engine_increment"]["batch_sync_ms"]
                               - t["systems"]["application_sum"]["batch_sync_ms"],
        } for t in trials],
    }

    output_dir.mkdir(parents=True)
    json_path = output_dir / "increment_pilot_summary.json"
    csv_path = output_dir / "increment_pilot_trials.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["trial_id", "seed", "workload_digest", "outcome", "execution_order",
                         "application_sum_sync_ms", "engine_increment_sync_ms", "engine_lww_sync_ms",
                         "increment_minus_application_sum_ms", "increment_scr_pct", "increment_rvar_pct",
                         "source_json"])
        for trial in payload["trials"]:
            values = trial["systems"]
            writer.writerow([trial["trial_id"], trial["seed"], trial["workload_digest"],
                             trial["outcome"], ">".join(trial["execution_order"]),
                             values["application_sum"]["batch_sync_ms"],
                             values["engine_increment"]["batch_sync_ms"],
                             values["engine_lww"]["batch_sync_ms"], trial["paired_delta_ms"],
                             values["engine_increment"]["scr_pct"],
                             values["engine_increment"]["rvar_pct"], trial["source_json"]])
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("json_paths", type=Path, nargs="+")
    args = parser.parse_args()
    json_path, csv_path = summarize(args.json_paths, args.output_dir)
    result = json.loads(json_path.read_text(encoding="utf-8"))
    print(json.dumps({"json": str(json_path), "csv": str(csv_path),
                      "trial_count": result["trial_count"],
                      "paired_delta_summary": result["paired_sync_delta_engine_increment_minus_application_sum"]},
                     indent=2))


if __name__ == "__main__":
    main()
