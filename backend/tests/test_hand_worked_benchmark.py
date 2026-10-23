"""Hand-worked engine regression for the additive benchmark case."""

import sqlite3
import time

from backend.engine.crdt_sync import CRDTSyncEngine


def _run_single_conflict(root, policy, value_a, value_b, common_hlc):
    root.mkdir()
    base = root / "base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE bench_rows(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO bench_rows(id, value) VALUES (1, 100)")

    engine = CRDTSyncEngine(base_db_path=str(base), data_dir=str(root / "replicas"))
    replica_a = engine.create_replica("bench_a")
    replica_b = engine.create_replica("bench_b")
    engine.apply_change(replica_a, "bench_a", "bench_rows", 1, "value", value_a, custom_hlc=common_hlc)
    engine.apply_change(replica_b, "bench_b", "bench_rows", 1, "value", value_b, custom_hlc=common_hlc)
    engine.sync_replicas(
        replica_a, replica_b, str(base), "bench_a", "bench_b",
        policies={"bench_rows": {"value": policy}},
    )

    values = []
    for replica in (replica_a, replica_b):
        with sqlite3.connect(replica) as conn:
            values.append(conn.execute("SELECT value FROM bench_rows WHERE id=1").fetchone()[0])
    return values


def test_hand_worked_additive_conflict_uses_real_replica_sync(tmp_path):
    # Independent scenario specification: two edits from the common base 100.
    base_value = 100
    contribution_a = 41
    contribution_b = 8
    value_a = base_value + contribution_a
    value_b = base_value + contribution_b
    expected_additive_value = base_value + contribution_a + contribution_b
    assert expected_additive_value == 149

    # Equal explicit HLCs make the LWW tie-break deterministic: bench_b sorts
    # after bench_a, so the actual engine should select B's value (108).
    common_hlc = (time.time() + 3600, 0)
    lww_values = _run_single_conflict(
        tmp_path / "lww", "LWW", value_a, value_b, common_hlc
    )
    semantic_values = _run_single_conflict(
        tmp_path / "semantic", "SUM", value_a, value_b, common_hlc
    )

    assert lww_values == [value_b, value_b]
    assert semantic_values == [expected_additive_value, expected_additive_value]
