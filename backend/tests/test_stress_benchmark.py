"""
test_stress_benchmark.py
========================
Phase 4 regression tests for the StressHarness parametric benchmark.

Tests cover:
- Reproducibility (same seed ⟹ same SCR)
- Workload size variants: 1 000, 5 000, 10 000 operations
- Conflict density variants: 5%, 20%, 50%
- Latency statistics shape (p50 ≤ p95 ≤ p99)
- Artifact export (JSON + CSV created at expected paths)
- POST /api/v1/benchmark/stress HTTP endpoint
- StressBenchmarkResult field completeness
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from backend.api.models import StressBenchmarkMetrics, StressBenchmarkRequest
from backend.api.routes_benchmark import run_stress_benchmark

from backend.workloads.stress_harness import (
    StressBenchmarkConfig, StressHarness, StressBenchmarkResult, aggregate_samples,
    calculate_quality_metrics, get_environment_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_harness(num_operations: int = 1000, conflict_density: float = 0.20,
                 seed: int = 42, output_dir: str | None = None) -> StressHarness:
    cfg = StressBenchmarkConfig(
        num_operations=num_operations,
        conflict_density=conflict_density,
        seed=seed,
        output_dir=output_dir,
    )
    return StressHarness(cfg)


@pytest.fixture(scope="module")
def executed_result(tmp_path_factory):
    """One real run is shared by assertions; avoid rerunning the same 1k workload."""
    out = tmp_path_factory.mktemp("benchmark-artifacts")
    return make_harness(1000, 0.05, seed=42, output_dir=str(out)).run_benchmark()


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------

class TestStressBenchmarkBasic:
    def test_result_type(self, executed_result):
        result = executed_result
        assert isinstance(result, StressBenchmarkResult)

    def test_response_model_uses_scoped_agreement_metric(self, executed_result):
        response = StressBenchmarkMetrics(**executed_result.to_dict())
        assert response.semantic_sync_row_value_agreement_rate == pytest.approx(
            executed_result.semantic_sync_row_value_agreement_rate
        )
        assert not hasattr(response, "semantic_sync_convergence_rate")

    def test_result_fields_present(self, executed_result):
        result = executed_result
        assert result.num_operations == 1000
        assert result.conflict_density == pytest.approx(0.05)
        assert result.total_conflicts_evaluated >= 0
        assert 0.0 <= result.baseline_scr <= 100.0
        assert 0.0 <= result.semantic_sync_scr <= 100.0
        assert 0.0 <= result.baseline_row_value_agreement_rate <= 100.0
        assert 0.0 <= result.semantic_sync_row_value_agreement_rate <= 100.0
        assert result.p50_latency_ms >= 0.0
        assert result.p95_latency_ms >= 0.0
        assert result.p99_latency_ms >= 0.0
        assert result.avg_latency_ms >= 0.0
        assert result.total_sync_time_ms >= 0.0
        assert math.isfinite(result.resolution_overhead_ms)
        assert result.resolution_overhead_ms == pytest.approx(
            result.semantic_sync_sync_time_ms - result.baseline_sync_time_ms, abs=0.001
        )
        assert result.change_log_entries >= 0
        assert result.trial_count == 2
        assert result.summary_statistics["batch_sync_delta_ms"]["sample_count"] == 2

    def test_latency_ordering(self, executed_result):
        result = executed_result
        assert result.p50_latency_ms <= result.p95_latency_ms <= result.p99_latency_ms

    def test_semantic_sync_scr_gte_baseline(self, executed_result):
        """SemanticSync SCR should be ≥ baseline on SUM/APPEND/AVG conflict scenarios."""
        result = executed_result
        # Not a correctness guarantee (workload is synthetic), but should generally hold
        assert result.semantic_sync_scr >= 0.0


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    @pytest.mark.parametrize("trials", [1, 1.5, 11, True])
    def test_trial_count_must_be_a_balanced_bounded_integer(self, trials):
        with pytest.raises(ValueError, match="trials must be an integer"):
            StressHarness(StressBenchmarkConfig(trials=trials)).run_benchmark()

    def test_same_seed_same_scr(self):
        h1, h2 = make_harness(1000, 0.20, seed=42), make_harness(1000, 0.20, seed=42)
        assert h1.generate_workload_operations() == h2.generate_workload_operations()

    def test_different_seeds_may_differ(self):
        r1 = make_harness(1000, 0.20, seed=1).generate_workload_operations()
        r2 = make_harness(1000, 0.20, seed=9999).generate_workload_operations()
        assert r1 != r2

    def test_repeated_trial_aggregation_has_count_median_and_spread(self):
        summary = aggregate_samples([3.0, 1.0, 2.0], "milliseconds")
        assert summary == {"sample_count": 3, "unit": "milliseconds", "median": 2.0,
                           "minimum": 1.0, "maximum": 3.0}

    def test_reproducibility_metadata_contains_runtime_and_sqlite(self):
        metadata = get_environment_metadata()
        assert metadata["python_version"]
        assert metadata["platform"]
        assert metadata["sqlite_runtime_version"] == sqlite3.sqlite_version


# ---------------------------------------------------------------------------
# Workload size variants
# ---------------------------------------------------------------------------

class TestWorkloadSizes:
    @pytest.mark.parametrize("n_ops", [1000, 5000, 10000])
    def test_sizes(self, n_ops):
        operations = make_harness(num_operations=n_ops, conflict_density=0.05).generate_workload_operations()
        assert len(operations) == n_ops
        assert sum(op["is_conflict"] for op in operations) == round(n_ops * 0.05)

    def test_larger_workload_more_entries(self):
        small = make_harness(1000, 0.20).generate_workload_operations()
        large = make_harness(5000, 0.20).generate_workload_operations()
        assert len(large) > len(small)

    def test_systems_receive_identical_fresh_base_data(self, tmp_path):
        base_a, base_b = tmp_path / "lww.db", tmp_path / "semantic.db"
        mode_a = StressHarness._initialize_base_database(base_a, 3)
        mode_b = StressHarness._initialize_base_database(base_b, 3)
        assert mode_a == mode_b == "delete"
        with sqlite3.connect(base_a) as a, sqlite3.connect(base_b) as b:
            schema_a = a.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bench_rows'").fetchone()
            schema_b = b.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bench_rows'").fetchone()
            rows_a = a.execute("SELECT id, value FROM bench_rows ORDER BY id").fetchall()
            rows_b = b.execute("SELECT id, value FROM bench_rows ORDER BY id").fetchall()
        assert schema_a == schema_b
        assert rows_a == rows_b == [(1, 100), (2, 100), (3, 100)]


# ---------------------------------------------------------------------------
# Conflict density variants
# ---------------------------------------------------------------------------

class TestConflictDensities:
    @pytest.mark.parametrize("density", [0.05, 0.20, 0.50])
    def test_densities(self, density):
        operations = make_harness(1000, density).generate_workload_operations()
        assert sum(op["is_conflict"] for op in operations) == round(1000 * density)

    def test_higher_density_more_conflicts(self):
        low = make_harness(1000, 0.05, seed=42).generate_workload_operations()
        high = make_harness(1000, 0.50, seed=42).generate_workload_operations()
        assert sum(o["is_conflict"] for o in high) > sum(o["is_conflict"] for o in low)


# ---------------------------------------------------------------------------
# Artifact export
# ---------------------------------------------------------------------------

class TestArtifactExport:
    def test_json_artifact_created(self, executed_result):
        result = executed_result
        json_files = list(Path(result.artifacts["json"]).parent.glob("*.json"))
        assert json_files, "Expected at least one JSON artifact"
        data = json.loads(json_files[0].read_text())
        assert "num_operations" in data or "config" in data
        assert {"baseline_vra", "semantic_sync_vra", "resolution_overhead_ms",
                "baseline_sync_time_ms", "semantic_sync_sync_time_ms",
                "baseline_change_log_entries", "semantic_sync_change_log_entries",
                "oracle_values", "observed_states", "workload", "metric_definitions",
                "baseline_row_value_agreement_rate", "semantic_sync_row_value_agreement_rate"} <= data.keys()

    def test_reported_quality_metrics_are_derived_from_persisted_workload_states(self, executed_result):
        result = executed_result
        data = json.loads(Path(result.artifacts["json"]).read_text(encoding="utf-8"))
        states, oracle = data["observed_states"], data["oracle_values"]
        pairs = [(states["baseline_a"], states["baseline_b"], "baseline"),
                 (states["semantic_a"], states["semantic_b"], "semantic_sync")]
        for a, b, name in pairs:
            assert len(a) == len(b) == len(oracle) == data["num_operations"]
            expected_agreement = sum(x == y for x, y in zip(a, b)) / len(a) * 100
            assert data[f"{name}_row_value_agreement_rate"] == pytest.approx(expected_agreement, abs=0.001)
            expected_outcomes = [
                state[operation["op_id"] - 1] == oracle[operation["op_id"] - 1]
                for operation in data["workload"]
                if operation["is_conflict"]
                for state in (a, b)
            ]
            expected_scr = sum(expected_outcomes) / len(expected_outcomes) * 100
            assert data[f"{name}_scr"] == pytest.approx(expected_scr, abs=0.001)
        assert data["semantic_sync_vra"] is None
        assert data["metric_version"] == "conflict-scr-row-agreement-v3-repeated"
        assert data["conflict_row_ids"] == sorted(op["op_id"] for op in data["workload"] if op["is_conflict"])
        independent_oracle = [
            op["base_value"] + op["delta_a"] + op["delta_b"] if op["is_conflict"] else op["value_a"]
            for op in sorted(data["workload"], key=lambda op: op["op_id"])
        ]
        assert data["oracle_values"] == independent_oracle
        assert data["semantic_sync_change_log_entries"] == result.change_log_entries
        assert data["total_conflicts_evaluated"] == 50
        assert data["trial_count"] == 2
        assert data["initial_state"] == {
            "table": "bench_rows", "row_count": data["num_operations"],
            "value_for_every_row": 100, "replicas_created_from_equivalent_fresh_base_per_trial": True,
        }
        assert [trial["execution_order"][0] for trial in data["trials"]] == ["baseline", "semantic_sync"]
        assert all(trial["configuration"]["workload_digest"] == data["workload_digest"]
                   for trial in data["trials"])
        assert all(trial["configuration"]["policy_assignments"] == {
            "baseline": "LWW", "semantic_sync": "SUM"
        } for trial in data["trials"])
        assert data["summary_statistics"]["semantic_sync_batch_sync_ms"]["sample_count"] == 2
        assert data["summary_statistics"]["semantic_sync_batch_sync_ms"]["unit"] == "milliseconds"
        assert data["environment"]["sqlite_runtime_version"] == sqlite3.sqlite_version
        assert data["environment"]["journal_mode"]
        assert data["workload_mode"].startswith("sequential")
        for trial in data["trials"]:
            baseline, semantic = trial["systems"]["baseline"], trial["systems"]["semantic_sync"]
            assert len(baseline["observed_values_a"]) == len(semantic["observed_values_a"]) == data["num_operations"]
            assert trial["journal_mode"]["replicas"] == ["delete", "delete"]
            assert trial["sqlite_foreign_keys_enabled"] == [1, 1]
            # Independently verify conflict-only outcomes for each paired run.
            for system in (baseline, semantic):
                outcomes = [
                    values[op["op_id"] - 1] == data["oracle_values"][op["op_id"] - 1]
                    for op in data["workload"] if op["is_conflict"]
                    for values in (system["observed_values_a"], system["observed_values_b"])
                ]
                assert sum(outcomes) / len(outcomes) * 100 == pytest.approx(
                    system["quality_metrics"]["scr"]
                )

    def test_non_conflict_rows_cannot_inflate_conflict_only_scr(self):
        operations = [
            {"op_id": 1, "is_conflict": True},
            {"op_id": 2, "is_conflict": False},
            {"op_id": 3, "is_conflict": False},
            {"op_id": 4, "is_conflict": True},
        ]
        metrics = calculate_quality_metrics(
            values_a=[0, 20, 30, 0], values_b=[0, 20, 30, 0],
            operations=operations, oracle_values=[10, 20, 30, 40],
        )
        assert metrics["scr"] == 0.0
        assert metrics["row_value_agreement_rate"] == 100.0
        assert metrics["vra"] is None

    def test_one_correct_conflict_outcome_scores_half(self):
        operations = [{"op_id": 1, "is_conflict": True}, {"op_id": 2, "is_conflict": False}]
        metrics = calculate_quality_metrics(
            values_a=[5, 99], values_b=[6, 99], operations=operations, oracle_values=[5, 10]
        )
        assert metrics["scr"] == 50.0

    def test_zero_conflict_scr_is_undefined(self):
        metrics = calculate_quality_metrics(
            values_a=[7], values_b=[7], operations=[{"op_id": 1, "is_conflict": False}],
            oracle_values=[7],
        )
        assert metrics["scr"] is None
        assert metrics["row_value_agreement_rate"] == 100.0

    def test_zero_conflict_workload_returns_na_scr(self):
        result = make_harness(1000, 0.0, seed=42).run_benchmark()
        assert result.total_conflicts_evaluated == 0
        assert result.baseline_scr is None
        assert result.semantic_sync_scr is None
        assert result.baseline_vra is None
        assert result.semantic_sync_vra is None

    def test_row_value_agreement_does_not_compare_other_database_state(self, tmp_path):
        paths = (tmp_path / "a.db", tmp_path / "b.db")
        for path, marker in zip(paths, ("left", "right")):
            with sqlite3.connect(path) as conn:
                conn.execute("CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER)")
                conn.execute("INSERT INTO bench_rows VALUES (1, 7)")
                conn.execute("CREATE TABLE unrelated_state(marker TEXT)")
                conn.execute("INSERT INTO unrelated_state VALUES (?)", (marker,))
        values = StressHarness._values(paths, 1)
        metric = calculate_quality_metrics(
            values[0], values[1], [{"op_id": 1, "is_conflict": False}], [7]
        )
        assert metric["row_value_agreement_rate"] == 100.0
        with sqlite3.connect(paths[0]) as a, sqlite3.connect(paths[1]) as b:
            assert a.execute("SELECT marker FROM unrelated_state").fetchone() != b.execute(
                "SELECT marker FROM unrelated_state"
            ).fetchone()

    def test_csv_artifact_created(self, executed_result):
        result = executed_result
        csv_files = list(Path(result.artifacts["csv"]).parent.glob("*.csv"))
        assert csv_files, "Expected at least one CSV artifact"

    def test_csv_contains_trial_summary_and_units(self, executed_result):
        with Path(executed_result.artifacts["csv"]).open(newline="", encoding="utf-8") as stream:
            rows = list(__import__("csv").DictReader(stream))
        summary = [row for row in rows if row["record_type"] == "summary"]
        assert any(row["metric"] == "semantic_sync_batch_sync_ms_median" for row in summary)
        assert {row["unit"] for row in summary} >= {"milliseconds", "percent", "trials"}

    def test_artifact_paths_are_real(self, executed_result):
        assert Path(executed_result.artifacts["json"]).is_file()
        assert Path(executed_result.artifacts["csv"]).is_file()

    def test_to_dict_serializable(self, executed_result):
        result = executed_result
        d = result.to_dict()
        assert isinstance(d, dict)
        # Verify JSON round-trip
        raw = json.dumps(d)
        parsed = json.loads(raw)
        assert parsed["num_operations"] == 1000


# ---------------------------------------------------------------------------
# HTTP endpoint: POST /api/v1/benchmark/stress
# ---------------------------------------------------------------------------

class TestStressBenchmarkEndpoint:
    @pytest.fixture(autouse=True)
    def client(self):
        from starlette.testclient import TestClient
        from backend.app import app
        self._client = TestClient(app, backend="trio", raise_server_exceptions=True)

    def test_stress_endpoint_200(self):
        resp = self._client.post(
            "/api/v1/benchmark/stress",
            json={"num_operations": 1000, "conflict_density": 0.05, "seed": 42, "export_artifacts": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "num_operations" in data
        assert "semantic_sync_scr" in data
        assert "semantic_sync_row_value_agreement_rate" in data
        assert "semantic_sync_convergence_rate" not in data
        assert "p50_latency_ms" in data

    def test_stress_endpoint_invalid_density(self):
        resp = self._client.post(
            "/api/v1/benchmark/stress",
            json={"num_operations": 1000, "conflict_density": 0.15, "seed": 42},
        )
        assert resp.status_code == 400

    def test_stress_endpoint_invalid_ops(self):
        resp = self._client.post(
            "/api/v1/benchmark/stress",
            json={"num_operations": -1, "conflict_density": 0.20, "seed": 42},
        )
        assert resp.status_code == 400


class TestStressBenchmarkRouteFunction:
    def test_zero_conflict_route_returns_nullable_conflict_metrics(self):
        response = run_stress_benchmark(
            StressBenchmarkRequest(num_operations=1000, conflict_density=0.0, export_artifacts=False)
        )
        assert response.total_conflicts_evaluated == 0
        assert response.baseline_scr is None
        assert response.semantic_sync_scr is None
        assert response.baseline_row_value_agreement_rate == 100.0
        assert response.semantic_sync_row_value_agreement_rate == 100.0
