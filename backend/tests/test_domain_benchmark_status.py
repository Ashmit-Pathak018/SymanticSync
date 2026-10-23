"""The legacy domain runner must not expose unvalidated comparisons."""

from backend.api.models import BenchmarkRequest
from backend.api.routes_benchmark import run_benchmark


def test_domain_runner_returns_status_without_comparative_values(monkeypatch):
    cached = {}
    monkeypatch.setattr(
        "backend.api.routes_benchmark.app_state.set_metrics",
        lambda name, value: cached.update({name: value}),
    )

    result = run_benchmark(BenchmarkRequest(workload="inventory"))
    payload = result.model_dump()

    assert payload["evaluation_status"] == "illustrative_unvalidated"
    assert "does not execute replica synchronization" in payload["explanation"]
    assert payload["workload"] == "inventory"
    for metric in (
        "baseline_scr",
        "semantic_sync_scr",
        "baseline_convergence_rate",
        "semantic_sync_convergence_rate",
        "resolution_overhead_ms",
        "total_conflicts_evaluated",
        "correct_semantic_outcomes",
    ):
        assert payload[metric] is None

    assert cached["inventory"] == payload
