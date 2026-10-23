"""Recompute SCR and inspect equal-assignment mismatches in saved stress runs.

This analysis is read-only. It does not rerun a benchmark or rewrite artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit(path: Path) -> dict[str, int | float | str]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    operations = artifact["workload"]
    conflict_ops = [operation for operation in operations if operation["is_conflict"]]
    denominator = 2 * len(conflict_ops)
    if denominator == 0:
        raise ValueError(f"{path}: no conflict rows; SCR is undefined")

    mismatch_ids: set[int] = set()
    equal_assignment_ids: set[int] = set()
    matched_values = 0
    for trial in artifact["trials"]:
        system = trial["systems"]["semantic_sync"]
        values_a = system["observed_values_a"]
        values_b = system["observed_values_b"]
        if len(values_a) != len(operations) or len(values_b) != len(operations):
            raise ValueError(f"{path}: trial {trial['trial_index']} observation length mismatch")
        trial_matches = 0
        for operation in conflict_ops:
            row_id = int(operation["op_id"])
            index = row_id - 1
            expected = int(operation["base_value"] + operation["delta_a"] + operation["delta_b"])
            if operation["value_a"] == operation["value_b"]:
                equal_assignment_ids.add(row_id)
            for observed in (values_a[index], values_b[index]):
                if observed == expected:
                    matched_values += 1
                    trial_matches += 1
                else:
                    mismatch_ids.add(row_id)
        recomputed = trial_matches / denominator * 100.0
        reported = float(system["quality_metrics"]["scr"])
        if abs(recomputed - reported) > 1e-9:
            raise ValueError(
                f"{path}: trial {trial['trial_index']} SCR mismatch: "
                f"recomputed {recomputed}, artifact {reported}"
            )

    non_equal_mismatches = mismatch_ids - equal_assignment_ids
    if non_equal_mismatches:
        raise ValueError(
            f"{path}: mismatch rows not explained by equal assignments: "
            f"{sorted(non_equal_mismatches)}"
        )
    scored_values = denominator * len(artifact["trials"])
    return {
        "configuration": f"{artifact['num_operations']}/{artifact['conflict_density']:.0%}",
        "trial_count": len(artifact["trials"]),
        "conflict_instances": len(conflict_ops) * len(artifact["trials"]),
        "equal_assignment_instances": sum(
            int(operation["value_a"] == operation["value_b"])
            for operation in conflict_ops
        ) * len(artifact["trials"]),
        "mismatching_conflict_rows": len(mismatch_ids) * len(artifact["trials"]),
        "scr_percent": matched_values / scored_values * 100.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?",
        default="artifacts/benchmarks/repeated-stress-20261014",
        type=Path,
    )
    args = parser.parse_args()
    files = sorted(args.directory.glob("benchmark_*_42.json"))
    if len(files) != 9:
        raise SystemExit(f"expected 9 repeated JSON artifacts under {args.directory}; found {len(files)}")
    print("operations/density | trials | conflict instances | equal assignments | mismatch rows | SCR")
    for path in files:
        result = audit(path)
        print(
            f"{result['configuration']:>17} | {result['trial_count']:>6} | "
            f"{result['conflict_instances']:>18} | {result['equal_assignment_instances']:>17} | "
            f"{result['mismatching_conflict_rows']:>13} | {result['scr_percent']:.2f}%"
        )
    print("PASS: recomputed SCR matches each trial; all mismatches are equal-assignment rows.")


if __name__ == "__main__":
    main()
