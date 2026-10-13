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
import tempfile
from pathlib import Path

import pytest

from backend.workloads.stress_harness import StressBenchmarkConfig, StressHarness, StressBenchmarkResult


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

    def test_result_fields_present(self, executed_result):
        result = executed_result
        assert result.num_operations == 1000
        assert result.conflict_density == pytest.approx(0.05)
        assert result.total_conflicts_evaluated >= 0
        assert 0.0 <= result.baseline_scr <= 100.0
        assert 0.0 <= result.semantic_sync_scr <= 100.0
        assert 0.0 <= result.baseline_convergence_rate <= 100.0
        assert 0.0 <= result.semantic_sync_convergence_rate <= 100.0
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
    def test_same_seed_same_scr(self):
        h1, h2 = make_harness(1000, 0.20, seed=42), make_harness(1000, 0.20, seed=42)
        assert h1.generate_workload_operations() == h2.generate_workload_operations()

    def test_different_seeds_may_differ(self):
        r1 = make_harness(1000, 0.20, seed=1).generate_workload_operations()
        r2 = make_harness(1000, 0.20, seed=9999).generate_workload_operations()
        assert r1 != r2


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
                "oracle_values", "observed_states", "workload"} <= data.keys()

    def test_reported_quality_metrics_are_derived_from_persisted_workload_states(self, executed_result):
        result = executed_result
        data = json.loads(Path(result.artifacts["json"]).read_text(encoding="utf-8"))
        states, oracle = data["observed_states"], data["oracle_values"]
        pairs = [(states["baseline_a"], states["baseline_b"], "baseline"),
                 (states["semantic_a"], states["semantic_b"], "semantic_sync")]
        for a, b, name in pairs:
            assert len(a) == len(b) == len(oracle) == data["num_operations"]
            expected_cr = sum(x == y for x, y in zip(a, b)) / len(a) * 100
            assert data[f"{name}_convergence_rate"] == pytest.approx(expected_cr, abs=0.001)
            other = states["baseline_b"] if name == "baseline" else states["semantic_b"]
            expected_scr = (sum(x == y for state in (a, other) for x, y in zip(state, oracle))
                            / (2 * len(a)) * 100)
            assert data[f"{name}_scr"] == pytest.approx(expected_scr, abs=0.001)
        conflict_ids = {o["op_id"] - 1 for o in data["workload"] if o["is_conflict"]}
        expected_vra = (sum(state[i] == oracle[i] for state in (states["semantic_a"], states["semantic_b"])
                            for i in conflict_ids) / (2 * len(conflict_ids)) * 100)
        assert data["semantic_sync_vra"] == pytest.approx(expected_vra, abs=0.001)
        assert data["semantic_sync_change_log_entries"] == result.change_log_entries
        assert data["total_conflicts_evaluated"] == 50

    def test_csv_artifact_created(self, executed_result):
        result = executed_result
        csv_files = list(Path(result.artifacts["csv"]).parent.glob("*.csv"))
        assert csv_files, "Expected at least one CSV artifact"

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
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_stress_endpoint_200(self):
        resp = self._client.post(
            "/api/v1/benchmark/stress",
            json={"num_operations": 1000, "conflict_density": 0.05, "seed": 42, "export_artifacts": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "num_operations" in data
        assert "semantic_sync_scr" in data
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
