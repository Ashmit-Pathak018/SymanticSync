import sqlite3
from contextlib import closing

from backend.engine.crdt_sync import CRDTSyncEngine
from research.experiments.engine_evaluation import (
    additive_oracle,
    evaluate_values,
    generate_trace,
    run_configuration,
    trace_digest,
)


def test_independent_seed_traces_are_reproducible_but_distinct():
    first = generate_trace(40, 0.25, 20261020)
    same = generate_trace(40, 0.25, 20261020)
    next_seed = generate_trace(40, 0.25, 20261021)

    assert first == same
    assert trace_digest(first) == trace_digest(same)
    assert trace_digest(first) != trace_digest(next_seed)
    assert sum(operation["is_conflict"] for operation in first) == 10


def test_additive_oracle_is_independent_and_conflict_only():
    operations = [
        {"op_id": 1, "is_conflict": True, "base": 100,
         "delta_a": 41, "delta_b": 8},
        {"op_id": 2, "is_conflict": False, "base": 100,
         "delta_a": 5, "delta_b": 0},
    ]

    expected = additive_oracle(operations)
    assert expected == {1: 149, 2: 105}

    metrics = evaluate_values(operations, [149, 0], [149, 0])
    assert metrics["oracle_specific_conflict_scr_pct"] == 100.0
    assert metrics["oracle_denominator"] == 2
    assert metrics["benchmark_row_value_agreement_pct"] == 100.0


def test_oracle_specific_scr_does_not_establish_lww_semantic_failure():
    operation = [{"op_id": 1, "is_conflict": True, "base": 100,
                  "delta_a": 41, "delta_b": 8}]
    # A deterministic LWW winner can be either branch; this metric intentionally
    # scores it against the additive oracle and therefore records zero matches.
    metrics = evaluate_values(operation, [141], [141])
    assert metrics["oracle_specific_conflict_scr_pct"] == 0.0
    assert additive_oracle(operation)[1] == 149


def test_equal_concurrent_assignments_are_a_counterexample_for_additive_intent(tmp_path):
    """Characterize a semantic ambiguity; this is not a desired-value assertion.

    The synthetic additive oracle treats two writes of 110 from a common base
    of 100 as two +10 contributions. The current engine sees equal resulting
    cell values and detects no conflict. Because the callers used absolute
    SET operations, the engine correctly has no explicit INCREMENT records
    from which to infer that both equal assignments represented contributions.
    The separate INCREMENT API records that intent and has its own 120-result
    regression in `test_sync.py::test_equal_increment_contributions_are_two_operations`.
    """
    base = tmp_path / "base.sqlite"
    with closing(sqlite3.connect(base)) as connection:
        connection.execute(
            "CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO bench_rows VALUES (1, 100)")
        connection.commit()

    engine = CRDTSyncEngine(base_db_path=str(base), data_dir=str(tmp_path / "replicas"))
    replica_a = engine.create_replica("equal_a")
    replica_b = engine.create_replica("equal_b")
    engine.apply_change(replica_a, "equal_a", "bench_rows", 1, "value", 110)
    engine.apply_change(replica_b, "equal_b", "bench_rows", 1, "value", 110)
    sync = engine.sync_replicas(
        replica_a, replica_b, str(base), "equal_a", "equal_b",
        policies={"bench_rows": {"value": "SUM"}},
    )

    observed = []
    for path in (replica_a, replica_b):
        with closing(sqlite3.connect(path)) as connection:
            observed.append(connection.execute(
                "SELECT value FROM bench_rows WHERE id=1"
            ).fetchone()[0])

    # Independently hand-calculate the declared contribution model: 100+10+10.
    expected_additive_value = 100 + (110 - 100) + (110 - 100)
    assert expected_additive_value == 120
    assert observed == [110, 110]
    assert sync.total_conflicts == 0


def test_small_engine_evaluation_records_balanced_independent_trials_and_units(tmp_path):
    result = run_configuration(20, 0.25, [101, 102, 103], tmp_path / "pilot")

    import json
    payload = json.loads((tmp_path / "pilot" / "engine_evaluation_20_25pct.json").read_text())
    assert result["successful_trials"] == payload["successful_trial_count"] == 3
    assert payload["source_snapshot"]["git_revision"]
    assert payload["source_snapshot"]["worktree_dirty"] is True
    assert "backend/engine/crdt_sync.py" in payload["source_snapshot"]["relevant_file_sha256"]
    assert "research/experiments/engine_evaluation.py" in payload["source_snapshot"]["relevant_file_sha256"]
    trials = payload["trials"]
    assert len({trial["workload_digest"] for trial in trials}) == 3
    assert [trial["execution_order"] for trial in trials] == [
        ["application_sum", "engine_sum", "engine_lww"],
        ["engine_sum", "engine_lww", "application_sum"],
        ["engine_lww", "application_sum", "engine_sum"],
    ]
    for system in ("application_sum", "engine_sum", "engine_lww"):
        summary = payload["trial_summaries"][system]
        assert summary["batch_sync_ms"]["unit"] == "ms"
        assert summary["oracle_specific_conflict_scr_pct"]["unit"] == "percent"
        assert summary["benchmark_row_value_agreement_pct"]["unit"] == "percent"
    for trial in trials:
        app = trial["systems"]["application_sum"]
        engine = trial["systems"]["engine_sum"]
        assert app["metrics"]["oracle_specific_conflict_scr_pct"] == 100.0
        assert engine["metrics"]["oracle_specific_conflict_scr_pct"] == 100.0
        assert app["observed_values_a"] == engine["observed_values_a"]
        assert app["observed_values_b"] == engine["observed_values_b"]
        assert "applied_changes" not in app["sync_result"]
        assert "applied_changes" not in engine["sync_result"]
