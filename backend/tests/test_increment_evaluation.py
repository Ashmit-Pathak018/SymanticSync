from __future__ import annotations

import csv
import json
import sqlite3

from research.experiments.increment_evaluation import run_configuration
from research.experiments.summarize_increment_runs import summarize
from research.experiments.validate_increment_evaluation import validate


def test_increment_experiment_records_reproducible_values_and_real_paired_delta(tmp_path):
    output = tmp_path / "increment-study"
    result = run_configuration(12, 0.5, [7301], output)
    payload = json.loads((output / "increment_evaluation_12_50pct.json").read_text(encoding="utf-8"))
    trial = payload["trials"][0]
    assert trial["outcome"] == "SUCCESS"
    assert trial["trial_id"] == "increment-12-0.5-7301"
    assert trial["started_at_utc"] and trial["finished_at_utc"]
    assert payload["source_snapshot"]["relevant_file_sha256"]["research/experiments/increment_evaluation.py"]
    assert trial["systems"]["engine_increment"]["write_sample_count"] == 18

    # Independent hand-coded scoring: count only generated conflict rows and
    # compare both observed replica values to base + each intended delta.
    operations = trial["operations"]
    inc = trial["systems"]["engine_increment"]
    conflict_rows = [op for op in operations if op["is_conflict"]]
    matched = 0
    for op in conflict_rows:
        expected = 100 + op["delta_a"] + op["delta_b"]
        matched += inc["observed_values_a"][op["op_id"] - 1] == expected
        matched += inc["observed_values_b"][op["op_id"] - 1] == expected
    independent_scr = 100.0 * matched / (2 * len(conflict_rows))
    assert independent_scr == 100.0
    assert inc["metrics"]["oracle_specific_conflict_scr_pct"] == independent_scr

    expected_delta = (inc["batch_sync_ms"]
                      - trial["systems"]["application_sum"]["batch_sync_ms"])
    assert result["paired_sync_delta_engine_increment_minus_application_sum_ms"]["sample_count"] == 1
    assert result["paired_sync_delta_engine_increment_minus_application_sum_ms"]["median"] == expected_delta
    with (output / "increment_evaluation_12_50pct.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert {row["system"] for row in rows} == {"application_sum", "engine_increment", "engine_lww"}
    assert payload["metric_definitions"]["vra"] == "Not measured."
    assert "do not establish a general performance advantage" in payload["metric_definitions"]["comparison"]

    pair = output / "trial_1_seed_7301"
    for name in ("inc_a", "inc_b"):
        db_path = pair / "engine_increment" / "replicas" / f"{name}.db"
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT value FROM bench_rows ORDER BY id").fetchall() == [
                (100 + op["delta_a"] + (op["delta_b"] if op["is_conflict"] else 0),)
                for op in sorted(operations, key=lambda item: item["op_id"])
            ]
            assert conn.execute(
                "SELECT COUNT(*) FROM _ss_change_log WHERE op_type='INCREMENT'"
            ).fetchone()[0] == 18

    validated = validate(output / "increment_evaluation_12_50pct.json")
    assert validated["trial_count"] == 1
    assert validated["median_delta_ms"] == expected_delta


def test_increment_artifact_validator_rejects_inconsistent_summary(tmp_path):
    output = tmp_path / "increment-corrupt-summary"
    run_configuration(8, 0.25, [8301], output)
    path = output / "increment_evaluation_8_25pct.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["paired_sync_delta_engine_increment_minus_application_sum_ms"]["median"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        validate(path)
    except ValueError as exc:
        assert "median mismatch" in str(exc)
    else:
        raise AssertionError("corrupt paired summary was accepted")


def test_increment_run_summarizer_validates_and_aggregates_independent_seeds(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_configuration(8, 0.25, [9301, 9302], first)
    run_configuration(8, 0.25, [9303], second)

    output = tmp_path / "pooled"
    json_path, csv_path = summarize(
        [first / "increment_evaluation_8_25pct.json",
         second / "increment_evaluation_8_25pct.json"], output)
    result = json.loads(json_path.read_text(encoding="utf-8"))
    assert result["status"] == "exploratory_not_confirmatory"
    assert result["trial_count"] == result["unique_seed_count"] == 3
    assert result["unique_workload_digest_count"] == 3
    assert result["paired_sync_delta_engine_increment_minus_application_sum"]["sample_count"] == 3
    assert result["paired_sync_delta_engine_increment_minus_application_sum"]["unit"] == "ms"
    assert len(result["trials"]) == 3
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert {int(row["seed"]) for row in rows} == {9301, 9302, 9303}


def test_increment_run_summarizer_accepts_one_run_and_reports_sample_count(tmp_path):
    source = tmp_path / "single"
    run_configuration(8, 0.25, [9351, 9352], source)

    json_path, csv_path = summarize(
        [source / "increment_evaluation_8_25pct.json"], tmp_path / "single-summary")
    result = json.loads(json_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == "increment-run-summary-v1"
    assert result["trial_count"] == result["unique_seed_count"] == 2
    assert result["paired_sync_delta_engine_increment_minus_application_sum"]["sample_count"] == 2
    assert len(result["trials"]) == 2
    with csv_path.open(newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 2


def test_increment_run_summarizer_rejects_incompatible_source_snapshots(tmp_path):
    first = tmp_path / "first-compatible"
    second = tmp_path / "second-incompatible"
    run_configuration(8, 0.25, [9401], first)
    run_configuration(8, 0.25, [9402], second)
    second_json = second / "increment_evaluation_8_25pct.json"
    payload = json.loads(second_json.read_text(encoding="utf-8"))
    payload["source_snapshot"]["relevant_file_sha256"]["backend/engine/crdt_sync.py"] = "0" * 64
    second_json.write_text(json.dumps(payload), encoding="utf-8")

    try:
        summarize([first / "increment_evaluation_8_25pct.json", second_json], tmp_path / "reject")
    except ValueError as exc:
        assert "incompatible source" in str(exc)
    else:
        raise AssertionError("records from incompatible sources were pooled")


def test_increment_run_summarizer_rejects_reused_seeds(tmp_path):
    first = tmp_path / "first-seed"
    second = tmp_path / "second-seed"
    run_configuration(8, 0.25, [9501], first)
    run_configuration(8, 0.25, [9501], second)

    try:
        summarize([first / "increment_evaluation_8_25pct.json",
                   second / "increment_evaluation_8_25pct.json"], tmp_path / "duplicate-seed")
    except ValueError as exc:
        assert "duplicate seed or workload digest" in str(exc)
    else:
        raise AssertionError("records with a reused seed were pooled")
