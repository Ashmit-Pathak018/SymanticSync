"""Validate saved repeated stress-benchmark artifacts without running workloads.

Usage from the repository root:
    python -m backend.workloads.validate_repeated_benchmark_artifacts
    python -m backend.workloads.validate_repeated_benchmark_artifacts PATH
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


EXPECTED_SIZES = (1000, 5000, 10000)
EXPECTED_DENSITIES = (0.05, 0.20, 0.50)
EXPECTED_SEED = 42
EXPECTED_TRIALS = 2
EXPECTED_METRIC_VERSION = "conflict-scr-row-agreement-v3-repeated"
CSV_HEADER = ["record_type", "trial_index", "system", "metric", "value", "unit", "execution_order"]
SYSTEMS = ("baseline", "semantic_sync")
ORDER_BY_TRIAL = {1: "baseline -> semantic_sync", 2: "semantic_sync -> baseline"}


class ValidationError(Exception):
    """Raised for malformed, incomplete, or inconsistent saved evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _same_number(actual: Any, expected: Any, label: str) -> None:
    _require(
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and math.isfinite(float(actual))
        and math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-9),
        f"{label}: expected {expected!r}, got {actual!r}",
    )


def _finite_number(value: Any, label: str, *, nonnegative: bool = False) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be numeric")
    result = float(value)
    _require(math.isfinite(result), f"{label} must be finite")
    if nonnegative:
        _require(result >= 0, f"{label} must be nonnegative")
    return result


def _csv_number(value: str, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be numeric, got {value!r}") from exc
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _check_summary(actual: dict[str, Any], values: list[float], unit: str, label: str) -> None:
    _require(isinstance(actual, dict), f"summary_statistics.{label} must be an object")
    _require(actual.get("sample_count") == len(values), f"{label}: sample_count mismatch")
    _require(actual.get("unit") == unit, f"{label}: unit mismatch")
    if not values:
        _require(
            actual.get("median") is None and actual.get("minimum") is None and actual.get("maximum") is None,
            f"{label}: empty summary must have null statistics",
        )
        return
    for key, expected in (
        ("median", statistics.median(values)),
        ("minimum", min(values)),
        ("maximum", max(values)),
    ):
        _same_number(actual.get(key), expected, f"{label}.{key}")


def _quality(values_a: list[int], values_b: list[int], workload: list[dict[str, Any]], oracle: list[int]) -> dict[str, float | None]:
    conflict_indices = [i for i, op in enumerate(workload) if op["is_conflict"]]
    scr = None
    if conflict_indices:
        correct = sum(
            observed[i] == oracle[i]
            for i in conflict_indices
            for observed in (values_a, values_b)
        )
        scr = correct / (2 * len(conflict_indices)) * 100.0
    rvar = sum(a == b for a, b in zip(values_a, values_b)) / len(workload) * 100.0 if workload else 100.0
    return {"scr": scr, "row_value_agreement_rate": rvar, "vra": None}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _csv_records(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            _require(reader.fieldnames == CSV_HEADER, f"{path.name}: unexpected CSV header")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationError(f"{path.name}: cannot read CSV: {exc}") from exc
    _require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
             f"{path.name}: malformed CSV row")
    return rows


def _check_csv(path: Path, payload: dict[str, Any], csv_rows: list[dict[str, str]]) -> None:
    aggregates: dict[str, str] = {}
    summaries: dict[str, str] = {}
    trial_rows: dict[tuple[int, str, str], dict[str, str]] = {}
    configs: dict[tuple[int, str], str] = {}
    write_samples: dict[tuple[int, str], list[tuple[int, float, str]]] = {}

    for row in csv_rows:
        kind = row["record_type"]
        if kind == "aggregate":
            key = row["metric"]
            _require(key not in aggregates, f"{path.name}: duplicate aggregate {key}")
            aggregates[key] = row["value"]
        elif kind == "summary":
            key = row["metric"]
            _require(key not in summaries, f"{path.name}: duplicate summary {key}")
            summaries[key] = row["value"]
        elif kind == "trial_configuration":
            index = int(row["trial_index"])
            key = (index, row["metric"])
            _require(key not in configs, f"{path.name}: duplicate trial configuration {key}")
            configs[key] = row["value"]
            _require(row["execution_order"] == ORDER_BY_TRIAL.get(index),
                     f"{path.name}: trial {index} execution order mismatch in configuration")
        elif kind == "trial":
            index = int(row["trial_index"])
            key = (index, row["system"], row["metric"])
            _require(key not in trial_rows, f"{path.name}: duplicate trial measurement {key}")
            trial_rows[key] = row
        elif kind == "tracked_write_sample":
            index = int(row["trial_index"])
            key = (index, row["system"])
            try:
                sample_index = int(row["metric"].removeprefix("write_"))
            except ValueError as exc:
                raise ValidationError(f"{path.name}: malformed tracked-write sample index") from exc
            write_samples.setdefault(key, []).append(
                (sample_index, _csv_number(row["value"], f"{path.name} {key} write sample"), row["execution_order"])
            )
            _require(row["unit"] == "milliseconds", f"{path.name}: tracked-write sample unit mismatch")
        else:
            raise ValidationError(f"{path.name}: unknown record_type {kind!r}")

    expected_aggregates = {
        key: value for key, value in payload.items()
        if isinstance(value, (str, int, float)) or value is None
    }
    _require(set(aggregates) == set(expected_aggregates), f"{path.name}: aggregate field set differs from JSON")
    for key, expected in expected_aggregates.items():
        value = aggregates[key]
        if expected is None:
            _require(value == "", f"{path.name}: aggregate {key} should be blank for null")
        elif isinstance(expected, str):
            _require(value == expected, f"{path.name}: aggregate {key} differs from JSON")
        else:
            _same_number(_csv_number(value, f"{path.name} aggregate {key}"), expected, f"CSV aggregate {key}")

    expected_summary = {
        f"{metric}_{stat}": summary[stat]
        for metric, summary in payload["summary_statistics"].items()
        for stat in ("sample_count", "median", "minimum", "maximum")
    }
    _require(set(summaries) == set(expected_summary), f"{path.name}: summary field set differs from JSON")
    for key, expected in expected_summary.items():
        if key.endswith("_sample_count"):
            metric_name = key[:-len("_sample_count")]
            expected_unit = "trials"
        else:
            metric_name, _statistic = key.rsplit("_", 1)
            expected_unit = payload["summary_statistics"][metric_name]["unit"]
        summary_row = next(row for row in csv_rows if row["record_type"] == "summary" and row["metric"] == key)
        _require(summary_row["unit"] == expected_unit, f"{path.name}: summary {key} unit mismatch")
        if expected is None:
            _require(summaries[key] == "", f"{path.name}: summary {key} should be blank")
        elif key.endswith("_sample_count"):
            _require(int(summaries[key]) == expected, f"{path.name}: summary {key} differs from JSON")
        else:
            _same_number(_csv_number(summaries[key], f"{path.name} summary {key}"), expected, f"CSV summary {key}")

    for trial in payload["trials"]:
        index = trial["trial_index"]
        order = ORDER_BY_TRIAL[index]
        config = trial["configuration"]
        for name, value in config.items():
            key = (index, name)
            _require(key in configs, f"{path.name}: missing CSV trial configuration {key}")
            if isinstance(value, dict):
                try:
                    parsed = json.loads(configs[key])
                except json.JSONDecodeError as exc:
                    try:
                        # Some saved CSVs stringify this metadata using Python's
                        # dict representation; accept only literal data here.
                        parsed = ast.literal_eval(configs[key])
                    except (ValueError, SyntaxError) as literal_exc:
                        raise ValidationError(f"{path.name}: malformed CSV configuration {key}") from literal_exc
                _require(parsed == value, f"{path.name}: CSV trial configuration {key} differs from JSON")
            else:
                _require(configs[key] == str(value), f"{path.name}: CSV trial configuration {key} differs from JSON")
        for system in SYSTEMS:
            run = trial["systems"][system]
            for metric, expected, unit in (
                ("batch_sync_ms", run["batch_sync_ms"], "milliseconds"),
                *((f"tracked_write_{name}", value, "milliseconds") for name, value in run["tracked_write_latency_ms"].items()),
            ):
                key = (index, system, metric)
                _require(key in trial_rows, f"{path.name}: missing CSV trial metric {key}")
                row = trial_rows[key]
                _require(row["execution_order"] == order and row["unit"] == unit,
                         f"{path.name}: CSV trial metadata mismatch for {key}")
                _same_number(_csv_number(row["value"], f"{path.name} {key}"), expected, f"CSV trial {key}")
            samples = sorted(write_samples.get((index, system), []))
            expected_count = payload["num_operations"] + payload["total_conflicts_evaluated"]
            _require(len(samples) == expected_count, f"{path.name}: trial {index} {system} has wrong write-sample count")
            _require([sample[0] for sample in samples] == list(range(1, expected_count + 1)),
                     f"{path.name}: trial {index} {system} write sample indices are incomplete or duplicated")
            _require(all(sample[2] == order for sample in samples),
                     f"{path.name}: trial {index} {system} write-sample order mismatch")
            latencies = [sample[1] for sample in samples]
            _require(all(value >= 0 for value in latencies),
                     f"{path.name}: trial {index} {system} has negative write latency")
            latency_stats = run["tracked_write_latency_ms"]
            for key, expected in (
                ("p50", _percentile(latencies, 0.50)),
                ("p95", _percentile(latencies, 0.95)),
                ("p99", _percentile(latencies, 0.99)),
                ("mean", statistics.mean(latencies)),
            ):
                _same_number(latency_stats[key], expected, f"JSON trial {index} {system} tracked-write {key}")
    expected_write_keys = {(trial["trial_index"], system) for trial in payload["trials"] for system in SYSTEMS}
    _require(set(write_samples) == expected_write_keys, f"{path.name}: missing or unexpected tracked-write sample groups")
    _require(len(configs) == len(payload["trials"]) * 7, f"{path.name}: unexpected CSV trial configuration count")
    _require(len(trial_rows) == len(payload["trials"]) * len(SYSTEMS) * 5,
             f"{path.name}: unexpected CSV trial measurement count")


def _validate_json(path: Path, csv_path: Path, density: float, size: int,
                   common_environment: dict[str, Any] | None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path.name}: cannot read JSON: {exc}") from exc
    _require(payload.get("metric_version") == EXPECTED_METRIC_VERSION, f"{path.name}: unsupported metric_version")
    _require(payload.get("num_operations") == size, f"{path.name}: num_operations mismatch")
    _require(payload.get("conflict_density") == density, f"{path.name}: conflict_density mismatch")
    _require(payload.get("config", {}).get("num_operations") == size, f"{path.name}: config size mismatch")
    _require(payload["config"].get("conflict_density") == density, f"{path.name}: config density mismatch")
    _require(payload["config"].get("seed") == EXPECTED_SEED, f"{path.name}: expected seed {EXPECTED_SEED}")
    _require(payload["config"].get("trials") == EXPECTED_TRIALS, f"{path.name}: expected two configured trials")
    _require(payload.get("trial_count") == EXPECTED_TRIALS, f"{path.name}: trial_count is not two")
    _require(payload.get("workload_mode") == "sequential local writes followed by batch synchronization",
             f"{path.name}: workload mode mismatch")
    definitions = payload.get("metric_definitions", {})
    _require("conflict rows only" in definitions.get("scr", ""), f"{path.name}: SCR definition is missing/conflicting")
    _require("ordered bench_rows.value" in definitions.get("row_value_agreement_rate", "")
             and "not full-database convergence" in definitions.get("row_value_agreement_rate", ""),
             f"{path.name}: row-value agreement definition is missing/conflicting")
    _require("Not measured" in definitions.get("vra", ""), f"{path.name}: VRA must remain unmeasured")
    boundaries = payload.get("timing_boundaries", {})
    _require(set(boundaries) == {"tracked_write_latency_ms", "batch_sync_ms", "batch_sync_delta_ms"},
             f"{path.name}: timing-boundary fields mismatch")
    _require("apply_change" in boundaries["tracked_write_latency_ms"]
             and "sync_replicas" in boundaries["batch_sync_ms"]
             and "minus LWW" in boundaries["batch_sync_delta_ms"],
             f"{path.name}: timing-boundary definitions are malformed")

    env = payload.get("environment")
    required_env = ("platform", "python_version", "machine", "processor", "sqlite_runtime_version", "journal_mode", "measurement_scope")
    _require(isinstance(env, dict) and all(env.get(k) for k in required_env), f"{path.name}: incomplete environment metadata")
    if common_environment is None:
        common_environment = {key: env[key] for key in required_env if key not in ("measurement_scope",)}
    else:
        for key in required_env:
            if key not in ("measurement_scope",):
                _require(env[key] == common_environment[key], f"{path.name}: environment {key} differs across matrix")

    workload = payload.get("workload")
    _require(isinstance(workload, list) and len(workload) == size, f"{path.name}: workload length mismatch")
    ordered = sorted(workload, key=lambda op: op.get("op_id", -1))
    _require([op.get("op_id") for op in ordered] == list(range(1, size + 1)), f"{path.name}: operation IDs are not unique and contiguous")
    expected_conflicts = int(round(size * density))
    conflict_ops = [op for op in ordered if op.get("is_conflict") is True]
    _require(len(conflict_ops) == expected_conflicts, f"{path.name}: conflict-row count mismatch")
    for op in ordered:
        _require(op.get("policy") == "SUM" and op.get("base_value") == 100, f"{path.name}: unexpected operation policy/base")
        _require(isinstance(op.get("is_conflict"), bool), f"{path.name}: malformed conflict flag")
        _require(isinstance(op.get("delta_a"), int) and 1 <= op["delta_a"] <= 50,
                 f"{path.name}: delta_a is outside the generator's integer range")
        _require(op.get("value_a") == op["base_value"] + op["delta_a"], f"{path.name}: value_a does not match delta")
        _require(op.get("delta_b") == (op["value_b"] - op["base_value"]), f"{path.name}: value_b does not match delta")
        if op["is_conflict"]:
            _require(isinstance(op["delta_b"], int) and 1 <= op["delta_b"] <= 50,
                     f"{path.name}: conflict delta_b is outside the generator's integer range")
            expected = op["base_value"] + op["delta_a"] + op["delta_b"]
        else:
            _require(op["delta_b"] == 0, f"{path.name}: non-conflict operation has a second contribution")
            expected = op["value_a"]
        _require(op.get("expected_semantic") == expected, f"{path.name}: workload oracle mismatch")

    digest = hashlib.sha256(json.dumps(workload, sort_keys=True).encode()).hexdigest()
    _require(payload.get("workload_digest") == digest, f"{path.name}: workload digest does not match operations")
    oracle = [op["expected_semantic"] for op in ordered]
    _require(payload.get("oracle_values") == oracle, f"{path.name}: oracle_values mismatch")
    conflict_ids = [op["op_id"] for op in conflict_ops]
    _require(payload.get("conflict_row_ids") == conflict_ids, f"{path.name}: conflict_row_ids mismatch")
    _require(payload.get("total_conflicts_evaluated") == expected_conflicts, f"{path.name}: conflict total mismatch")
    _require(payload.get("initial_state") == {
        "table": "bench_rows", "row_count": size, "value_for_every_row": 100,
        "replicas_created_from_equivalent_fresh_base_per_trial": True,
    }, f"{path.name}: initial-state description mismatch")

    trials = payload.get("trials")
    _require(isinstance(trials, list) and len(trials) == EXPECTED_TRIALS, f"{path.name}: expected exactly two trial records")
    expected_policies = {"baseline": "LWW", "semantic_sync": "SUM"}
    expected_sync = "sequential tracked writes followed by pairwise batch sync"
    for index, trial in enumerate(trials, start=1):
        _require(trial.get("trial_index") == index, f"{path.name}: missing/duplicate trial index {index}")
        expected_order = ["baseline", "semantic_sync"] if index == 1 else ["semantic_sync", "baseline"]
        _require(trial.get("execution_order") == expected_order, f"{path.name}: trial {index} order mismatch")
        config = trial.get("configuration", {})
        for name, expected in (("num_operations", size), ("conflict_density", density), ("seed", EXPECTED_SEED), ("trials", EXPECTED_TRIALS)):
            _require(config.get(name) == expected, f"{path.name}: trial {index} {name} mismatch")
        _require(config.get("workload_digest") == digest, f"{path.name}: trial {index} digest mismatch")
        _require(config.get("policy_assignments") == expected_policies, f"{path.name}: trial {index} policies mismatch")
        _require(config.get("sync_mode") == expected_sync, f"{path.name}: trial {index} sync mode mismatch")
        _require(trial.get("journal_mode") == {"base": "delete", "replicas": ["delete", "delete"]},
                 f"{path.name}: trial {index} journal modes mismatch")
        _require(trial.get("sqlite_foreign_keys_enabled") == [1, 1], f"{path.name}: trial {index} FK setting mismatch")
        systems = trial.get("systems", {})
        _require(set(systems) == set(SYSTEMS), f"{path.name}: trial {index} has missing/extra system records")
        for system in SYSTEMS:
            run = systems[system]
            _finite_number(run.get("batch_sync_ms"), f"{path.name} trial {index} {system} sync", nonnegative=True)
            _require(isinstance(run.get("change_log_entries"), int) and run["change_log_entries"] >= 0,
                     f"{path.name}: trial {index} {system} receipt count malformed")
            for field in ("observed_values_a", "observed_values_b"):
                values = run.get(field)
                _require(isinstance(values, list) and len(values) == size, f"{path.name}: trial {index} {system} {field} length mismatch")
                _require(all(isinstance(value, int) and not isinstance(value, bool) for value in values),
                         f"{path.name}: trial {index} {system} {field} contains non-integer values")
            expected_quality = _quality(run["observed_values_a"], run["observed_values_b"], ordered, oracle)
            quality = run.get("quality_metrics", {})
            _require(quality.get("vra") is None, f"{path.name}: stress VRA must remain unmeasured")
            for key, expected in expected_quality.items():
                if expected is None:
                    _require(quality.get(key) is None, f"{path.name}: trial {index} {system} {key} should be null")
                else:
                    _same_number(quality.get(key), expected, f"{path.name} trial {index} {system} {key}")
            latency = run.get("tracked_write_latency_ms", {})
            _require(set(latency) == {"p50", "p95", "p99", "mean"}, f"{path.name}: trial {index} {system} latency fields malformed")
            for key, value in latency.items():
                _finite_number(value, f"{path.name} trial {index} {system} {key}", nonnegative=True)

    if "engine_settings" in payload:
        _require(payload["engine_settings"] == {
            "baseline_policy": "LWW", "semantic_sync_policy": "SUM",
            "sync_mode": expected_sync, "foreign_keys_enabled_on_tracked_engine_connections": True,
        }, f"{path.name}: optional engine_settings disagree with recorded trials")

    summary = payload.get("summary_statistics")
    _require(isinstance(summary, dict), f"{path.name}: missing summary_statistics")
    sources: dict[str, list[float]] = {}
    for system in SYSTEMS:
        sources[f"{system}_scr_pct"] = [float(t["systems"][system]["quality_metrics"]["scr"]) for t in trials]
        sources[f"{system}_row_value_agreement_pct"] = [float(t["systems"][system]["quality_metrics"]["row_value_agreement_rate"]) for t in trials]
        for field, summary_name in (("p50", "p50"), ("p95", "p95"), ("p99", "p99"), ("mean", "mean")):
            sources[f"{system}_tracked_write_{summary_name}_ms"] = [float(t["systems"][system]["tracked_write_latency_ms"][field]) for t in trials]
        sources[f"{system}_batch_sync_ms"] = [float(t["systems"][system]["batch_sync_ms"]) for t in trials]
    sources["batch_sync_delta_ms"] = [
        float(t["systems"]["semantic_sync"]["batch_sync_ms"] - t["systems"]["baseline"]["batch_sync_ms"])
        for t in trials
    ]
    _require(set(summary) == set(sources), f"{path.name}: summary metric set mismatch")
    for name, values in sources.items():
        unit = "percent" if name.endswith("_pct") else "milliseconds"
        _check_summary(summary[name], values, unit, name)

    def med(key: str) -> float:
        return statistics.median(sources[key])

    expected_top = {
        "baseline_scr": round(med("baseline_scr_pct"), 4),
        "semantic_sync_scr": round(med("semantic_sync_scr_pct"), 4),
        "baseline_row_value_agreement_rate": round(med("baseline_row_value_agreement_pct"), 4),
        "semantic_sync_row_value_agreement_rate": round(med("semantic_sync_row_value_agreement_pct"), 4),
        "p50_latency_ms": med("semantic_sync_tracked_write_p50_ms"),
        "p95_latency_ms": med("semantic_sync_tracked_write_p95_ms"),
        "p99_latency_ms": med("semantic_sync_tracked_write_p99_ms"),
        "avg_latency_ms": med("semantic_sync_tracked_write_mean_ms"),
        "baseline_sync_time_ms": med("baseline_batch_sync_ms"),
        "semantic_sync_sync_time_ms": med("semantic_sync_batch_sync_ms"),
        "total_sync_time_ms": med("semantic_sync_batch_sync_ms"),
        "resolution_overhead_ms": med("batch_sync_delta_ms"),
        "baseline_change_log_entries": statistics.median([t["systems"]["baseline"]["change_log_entries"] for t in trials]),
        "semantic_sync_change_log_entries": statistics.median([t["systems"]["semantic_sync"]["change_log_entries"] for t in trials]),
        "change_log_entries": int(statistics.median([t["systems"]["semantic_sync"]["change_log_entries"] for t in trials])),
    }
    for key, expected in expected_top.items():
        _same_number(payload.get(key), expected, f"{path.name} top-level {key}")
    _require(payload.get("baseline_vra") is None and payload.get("semantic_sync_vra") is None,
             f"{path.name}: VRA must remain unmeasured")
    for key, system in (("baseline_a", "baseline"), ("baseline_b", "baseline"),
                        ("semantic_a", "semantic_sync"), ("semantic_b", "semantic_sync")):
        field = "observed_values_a" if key.endswith("_a") else "observed_values_b"
        _require(payload["observed_states"].get(key) == trials[0]["systems"][system][field],
                 f"{path.name}: observed_states.{key} does not match trial 1")

    csv_rows = _csv_records(csv_path)
    _check_csv(csv_path, payload, csv_rows)
    return {
        "size": size,
        "density": density,
        "digest": digest,
        "deltas_ms": sources["batch_sync_delta_ms"],
        "environment": common_environment,
        "engine_settings_present": "engine_settings" in payload,
    }


def validate_directory(directory: Path) -> list[dict[str, Any]]:
    _require(directory.is_dir(), f"artifact directory does not exist: {directory}")
    expected_pairs = {
        f"benchmark_{size}_{int(density * 100)}pct_{EXPECTED_SEED}"
        for size in EXPECTED_SIZES
        for density in EXPECTED_DENSITIES
    }
    json_stems = {path.stem for path in directory.glob("*.json")}
    csv_stems = {path.stem for path in directory.glob("*.csv")}
    _require(json_stems == expected_pairs, f"JSON file set mismatch; missing={sorted(expected_pairs-json_stems)}, extra={sorted(json_stems-expected_pairs)}")
    _require(csv_stems == expected_pairs, f"CSV file set mismatch; missing={sorted(expected_pairs-csv_stems)}, extra={sorted(csv_stems-expected_pairs)}")
    _require(len(list(directory.glob("*.json"))) == 9 and len(list(directory.glob("*.csv"))) == 9,
             "expected nine JSON and nine CSV files")

    results = []
    common_environment = None
    for size in EXPECTED_SIZES:
        for density in EXPECTED_DENSITIES:
            stem = f"benchmark_{size}_{int(density * 100)}pct_{EXPECTED_SEED}"
            result = _validate_json(directory / f"{stem}.json", directory / f"{stem}.csv", density, size, common_environment)
            common_environment = result["environment"]
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate saved repeated SemanticSync stress artifacts without rerunning benchmarks.")
    parser.add_argument("directory", nargs="?", type=Path, default=Path("artifacts/benchmarks/repeated-stress-20261014"))
    args = parser.parse_args()
    try:
        results = validate_directory(args.directory)
    except (ValidationError, KeyError, TypeError, ValueError, OverflowError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    for item in results:
        delta_a, delta_b = item["deltas_ms"]
        print(f"OK {item['size']:>5} ops / {item['density']:>4.0%}: 2 paired trials; deltas {delta_a:.2f}, {delta_b:.2f} ms; digest {item['digest'][:12]}")
    print(f"VALIDATION PASSED: {len(results)} configurations, 18 artifacts, 18 paired trials; no benchmark was run.")
    absent_settings = sum(not item["engine_settings_present"] for item in results)
    if absent_settings:
        print(f"NOTE: redundant top-level engine_settings is absent in {absent_settings}/9 JSON files; trial-level policy, sync, FK, and journal metadata were validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
