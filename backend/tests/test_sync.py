"""
test_sync.py
=============
Pytest tests for CRDTSyncEngine and replica synchronization.
"""

import sqlite3
from pathlib import Path
import pytest

from backend.engine.crdt_sync import CRDTSyncEngine


def test_replica_creation_and_sync(tmp_path: Path):
    base_db = tmp_path / "base.db"
    conn = sqlite3.connect(str(base_db))
    conn.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, sku TEXT, quantity INTEGER, notes TEXT);")
    conn.execute("INSERT INTO inventory VALUES (1, 'ITEM-A', 100, 'Initial note');")
    conn.commit()
    conn.close()

    engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
    replica_a_path = engine.create_replica("device_a")
    replica_b_path = engine.create_replica("device_b")

    # Apply divergent changes to replica A and B
    # A adds 10 to quantity (110)
    engine.apply_change(
        replica_db_path=replica_a_path,
        replica_id="device_a",
        table="inventory",
        row_id=1,
        column="quantity",
        new_value=110,
    )

    # B adds 25 to quantity (125)
    engine.apply_change(
        replica_db_path=replica_b_path,
        replica_id="device_b",
        table="inventory",
        row_id=1,
        column="quantity",
        new_value=125,
    )

    # Configure SUM policy for quantity
    policies = {
        "inventory": {
            "quantity": "SUM",
            "notes": "APPEND",
        }
    }

    # Run sync
    sync_result = engine.sync_replicas(
        replica_a_path=replica_a_path,
        replica_b_path=replica_b_path,
        base_path=str(base_db),
        replica_a_id="device_a",
        replica_b_id="device_b",
        policies=policies,
    )

    assert sync_result.total_conflicts == 1
    assert sync_result.auto_resolved == 1

    # Verify both replicas converged to 135 (100 + 10 + 25)
    for p in (replica_a_path, replica_b_path):
        c = sqlite3.connect(p)
        row = c.execute("SELECT quantity FROM inventory WHERE id = 1").fetchone()
        c.close()
        assert row[0] == 135


def test_increment_operations_preserve_two_independent_contributions_and_replay_once(tmp_path: Path):
    base = tmp_path / "base_increment.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment"))
    a = engine.create_replica("inc_a")
    b = engine.create_replica("inc_b")

    operation_a = engine.apply_increment(a, "inc_a", "counters", 1, "value", 41)
    operation_b = engine.apply_increment(b, "inc_b", "counters", 1, "value", 8)
    assert operation_a != operation_b

    first = engine.sync_replicas(a, b, str(base), "inc_a", "inc_b", policies={"counters": {"value": "SUM"}})
    assert first.rejected_operations == []
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 149
            receipts = conn.execute(
                "SELECT origin_id,op_type FROM _ss_change_log WHERE op_type='INCREMENT' ORDER BY origin_id"
            ).fetchall()
            assert sorted(row[0] for row in receipts) == sorted((operation_a, operation_b))

    # New engine instance models restart. Repeated sync must be idempotent.
    restarted = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment"))
    restarted.sync_replicas(a, b, str(base), "inc_a", "inc_b", policies={"counters": {"value": "SUM"}})
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 149
            assert conn.execute(
                "SELECT COUNT(*) FROM _ss_change_log WHERE origin_id IN (?,?)",
                (operation_a, operation_b),
            ).fetchone()[0] == 2


def test_increment_delivery_accepts_reordered_operations_and_deduplicates(tmp_path: Path):
    base = tmp_path / "base_reordered.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_reordered"))
    source = engine.create_replica("inc_source")
    target = engine.create_replica("inc_target")
    first = engine.apply_increment(source, "inc_source", "counters", 1, "value", 41)
    second = engine.apply_increment(source, "inc_source", "counters", 1, "value", 8)
    with sqlite3.connect(source) as conn:
        events = conn.execute(
            "SELECT old_value,new_value,op_type,origin_id,source_id,source_sequence,ts_pt,ts_l,depends_on "
            "FROM _ss_change_log WHERE op_type='INCREMENT' ORDER BY sequence DESC"
        ).fetchall()
    known = {first, second}
    for old, delta, kind, origin, source_id, source_seq, ts_pt, ts_l, dependencies in events:
        status, reason = engine._apply_received_operation(
            target, "inc_target", "counters", 1, "value", old, delta, kind, origin,
            source_id, source_seq, ts_pt, ts_l, known, dependencies,
        )
        assert (status, reason) == ("applied", None)

    # Re-delivery of the newer operation returns duplicate without applying it again.
    old, delta, kind, origin, source_id, source_seq, ts_pt, ts_l, dependencies = events[0]
    status, reason = engine._apply_received_operation(
        target, "inc_target", "counters", 1, "value", old, delta, kind, origin,
        source_id, source_seq, ts_pt, ts_l, known, dependencies,
    )
    assert (status, reason) == ("duplicate", None)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 149
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='INCREMENT'").fetchone()[0] == 2


def test_increment_preserves_large_integer_precision(tmp_path: Path):
    base = tmp_path / "base_large_increment.db"
    start = 2**53 + 17
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,?)", (start,))
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_large_increment"))
    replica = engine.create_replica("large_inc")
    operation_id = engine.apply_increment(replica, "large_inc", "counters", 1, "value", 3)
    with sqlite3.connect(replica) as conn:
        assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == start + 3
        assert conn.execute(
            "SELECT op_type,old_value,new_value FROM _ss_change_log WHERE origin_id=?", (operation_id,)
        ).fetchone() == ("INCREMENT", str(start), "3")


def test_equal_increment_contributions_are_two_operations(tmp_path: Path):
    base = tmp_path / "base_equal_increment.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_equal_increment"))
    a = engine.create_replica("equal_a")
    b = engine.create_replica("equal_b")
    first = engine.apply_increment(a, "equal_a", "counters", 1, "value", 10)
    second = engine.apply_increment(b, "equal_b", "counters", 1, "value", 10)
    assert first != second
    engine.sync_replicas(a, b, str(base), "equal_a", "equal_b", policies={"counters": {"value": "SUM"}})
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 120
            assert conn.execute(
                "SELECT COUNT(DISTINCT origin_id) FROM _ss_change_log WHERE op_type='INCREMENT'"
            ).fetchone()[0] == 2


def test_concurrent_local_increment_calls_do_not_lose_contributions(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    base = tmp_path / "base_concurrent_increment.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_concurrent_increment"))
    replica = engine.create_replica("thread_inc")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(
            lambda _: engine.apply_increment(replica, "thread_inc", "counters", 1, "value", 1),
            range(12),
        ))
    assert len(set(ids)) == 12
    with sqlite3.connect(replica) as conn:
        assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 112
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='INCREMENT'").fetchone()[0] == 12


def test_increment_api_returns_applied_operation_and_materialized_value(tmp_path: Path, monkeypatch):
    import backend.api.routes_sync as routes
    from backend.api.state import AppState

    base = tmp_path / "base_increment_api.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment_api"))
    replica_path = engine.create_replica("api_inc")
    state = AppState()
    state.replicas = {"api_inc": {"replica_id": "api_inc", "db_path": replica_path,
                                   "parent_db_id": "db_increment"}}
    monkeypatch.setattr(routes, "app_state", state)
    monkeypatch.setattr(routes, "_sync_engine", engine)
    result = routes.apply_increment(routes.IncrementRequest(
        db_id="db_increment", replica_id="api_inc", table="counters", row_id=1,
        column="value", delta=7,
    ))
    assert result["status"] == "applied"
    assert result["value"] == 107
    with sqlite3.connect(replica_path) as conn:
        assert conn.execute(
            "SELECT op_type FROM _ss_change_log WHERE origin_id=?", (result["operation_id"],)
        ).fetchone() == ("INCREMENT",)


def test_increment_does_not_overwrite_a_concurrent_absolute_set(tmp_path: Path):
    base = tmp_path / "base_increment_set.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment_set"))
    a = engine.create_replica("mix_a")
    b = engine.create_replica("mix_b")
    engine.apply_increment(a, "mix_a", "counters", 1, "value", 41)
    engine.apply_change(b, "mix_b", "counters", 1, "value", 108)

    result = engine.sync_replicas(
        a, b, str(base), "mix_a", "mix_b", policies={"counters": {"value": "REJECT"}},
    )
    assert result.flagged_for_review == 1
    assert result.rejected_operations
    with sqlite3.connect(a) as conn_a, sqlite3.connect(b) as conn_b:
        assert conn_a.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 141
        assert conn_b.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 108


@pytest.mark.parametrize("trigger_sql", [
    "CREATE TRIGGER ignore_increment BEFORE UPDATE ON counters BEGIN SELECT RAISE(IGNORE); END",
    "CREATE TRIGGER mutate_increment AFTER UPDATE ON counters BEGIN UPDATE counters SET value=value+1 WHERE id=NEW.id; END",
])
def test_increment_trigger_mismatch_rolls_back_value_and_operation_log(tmp_path: Path, trigger_sql: str):
    base = tmp_path / "base_increment_trigger.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
        conn.execute(trigger_sql)
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment_trigger"))
    replica = engine.create_replica("trigger_inc")
    with pytest.raises(RuntimeError):
        engine.apply_increment(replica, "trigger_inc", "counters", 1, "value", 5)
    with sqlite3.connect(replica) as conn:
        assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='INCREMENT'").fetchone()[0] == 0


def test_increment_rejects_boolean_and_nonfinite_deltas(tmp_path: Path):
    base = tmp_path / "base_increment_invalid.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters(id INTEGER PRIMARY KEY, value REAL NOT NULL)")
        conn.execute("INSERT INTO counters VALUES(1,100)")
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_increment_invalid"))
    replica = engine.create_replica("invalid_inc")
    for delta in (True, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            engine.apply_increment(replica, "invalid_inc", "counters", 1, "value", delta)
    with sqlite3.connect(replica) as conn:
        assert conn.execute("SELECT value FROM counters WHERE id=1").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='INCREMENT'").fetchone()[0] == 0
