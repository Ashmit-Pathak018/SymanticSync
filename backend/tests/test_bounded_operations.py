"""BOUNDED_SUM invariant-safety and tracked signed-delta regressions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.policy_registry import parse_bounded_sum_bounds
from backend.engine.policy_validator import PolicyValidator
from backend.engine.semantic_resolver import ResolutionError, SemanticResolver


POLICY = "BOUNDED_SUM[min=0,max=100]"


def _world(tmp_path, initial=50):
    base = tmp_path / "base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES (1, ?)", (initial,))
        conn.commit()
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas"))
    return base, engine


def _value(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0]


def _operations(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT origin_id,source_id,source_sequence,bounded_delta,bounds_min,bounds_max "
            "FROM _ss_change_log WHERE bounded_delta IS NOT NULL ORDER BY source_id,source_sequence"
        ).fetchall()


def test_bounds_are_explicit_inclusive_and_validated():
    assert parse_bounded_sum_bounds(POLICY) == (0, 100)
    assert PolicyValidator.validate(POLICY, "INTEGER").valid
    assert not PolicyValidator.validate("BOUNDED_SUM", "INTEGER").valid
    assert not PolicyValidator.validate("BOUNDED_SUM[min=5,max=1]", "INTEGER").valid
    exact_min = 2**53 + 1
    exact_max = exact_min + 2
    assert parse_bounded_sum_bounds(
        f"BOUNDED_SUM[min={exact_min},max={exact_max}]"
    ) == (exact_min, exact_max)
    for value in (0, 100):
        result = SemanticResolver.resolve(
            "BOUNDED_SUM", 50, value, 50, min_bound=0, max_bound=100
        )
        assert result.status == "resolved" and result.resolved_value == value


@pytest.mark.parametrize(("a", "b", "expected", "status"), [
    (90, 70, 110, "flagged"),  # overflow
    (0, 0, -50, "flagged"),  # underflow
    (100, 50, 100, "resolved"),
    (0, 50, 0, "resolved"),
])
def test_resolver_flags_out_of_bound_combined_deltas_without_clamping(a, b, expected, status):
    result = SemanticResolver.resolve(
        "BOUNDED_SUM", 50, a, b, min_bound=0, max_bound=100
    )
    assert result.status == status
    assert result.resolved_value == expected
    assert "pending" in result.explanation if status == "flagged" else "within bounds" in result.explanation


def test_bounded_resolver_rejects_missing_or_non_numeric_bounds():
    with pytest.raises(ResolutionError, match="explicit"):
        SemanticResolver.resolve("BOUNDED_SUM", 50, 60, 40)
    with pytest.raises(ResolutionError, match="numeric"):
        SemanticResolver.resolve("BOUNDED_SUM", 50, "60", 40, min_bound=0, max_bound=100)


def test_tracked_write_logs_signed_delta_and_rejects_out_of_bounds_atomically(tmp_path):
    _base, engine = _world(tmp_path)
    replica = engine.create_replica("tracked")
    op_id = engine.apply_change(replica, "tracked", "counters", 1, "amount", 100,
                                bounded_bounds=(0, 100))
    assert _value(replica) == 100
    event = _operations(replica)[0]
    assert event == (op_id, "tracked", 1, 50.0, 0.0, 100.0)
    with pytest.raises(ValueError, match="outside inclusive bounds"):
        engine.apply_change(replica, "tracked", "counters", 1, "amount", 101,
                            bounded_bounds=(0, 100))
    assert _value(replica) == 100
    assert len(_operations(replica)) == 1


@pytest.mark.parametrize(("trigger_sql", "message"), [
    (
        "CREATE TRIGGER ignore_amount BEFORE UPDATE OF amount ON counters "
        "BEGIN SELECT RAISE(IGNORE); END",
        "did not affect exactly one row",
    ),
    (
        "CREATE TRIGGER mutate_amount AFTER UPDATE OF amount ON counters "
        "BEGIN UPDATE counters SET amount=999 WHERE id=NEW.id; END",
        "stored value",
    ),
])
def test_bounded_triggers_cannot_leave_state_without_a_valid_receipt(tmp_path, trigger_sql, message):
    _base, engine = _world(tmp_path)
    replica = engine.create_replica("triggered")
    with sqlite3.connect(replica) as conn:
        conn.execute(trigger_sql)

    with pytest.raises(RuntimeError, match=message):
        engine.apply_change(
            replica, "triggered", "counters", 1, "amount", 60,
            bounded_bounds=(0, 100),
        )

    assert _value(replica) == 50
    with sqlite3.connect(replica) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM _ss_change_log WHERE table_name='counters'"
        ).fetchone()[0] == 0


def test_bounds_above_binary64_exact_integer_range_persist_and_apply_exactly(tmp_path):
    minimum = 2**53 + 1
    maximum = minimum + 2
    policy = f"BOUNDED_SUM[min={minimum},max={maximum}]"
    base, engine = _world(tmp_path, initial=minimum)
    replica = engine.create_replica("large_integer")
    target = engine.create_replica("large_integer_target")
    bounds = parse_bounded_sum_bounds(policy)

    engine.apply_change(
        replica, "large_integer", "counters", 1, "amount", maximum,
        bounded_bounds=bounds,
    )
    assert _value(replica) == maximum
    with sqlite3.connect(replica) as conn:
        delta, stored_min, stored_max = conn.execute(
            "SELECT bounded_delta,bounds_min,bounds_max FROM _ss_change_log "
            "WHERE bounded_delta IS NOT NULL"
        ).fetchone()
        assert (delta, stored_min, stored_max) == (2, minimum, maximum)

    restarted = CRDTSyncEngine(str(base), str(tmp_path / "replicas"))
    sync_result = restarted.sync_replicas(
        replica, target, str(base), "large_integer", "large_integer_target",
        {"counters": {"amount": policy}},
    )
    assert not sync_result.rejected_operations
    assert _value(replica) == _value(target) == maximum
    with sqlite3.connect(target) as conn:
        receipt = conn.execute(
            "SELECT bounded_delta,bounds_min,bounds_max FROM _ss_change_log "
            "WHERE bounded_delta IS NOT NULL"
        ).fetchone()
        assert receipt == (2, minimum, maximum)

    with pytest.raises(ValueError, match="outside inclusive bounds"):
        engine.apply_change(
            replica, "large_integer", "counters", 1, "amount", minimum - 1,
            bounded_bounds=bounds,
        )
    assert _value(replica) == maximum
    assert len(_operations(replica)) == 1


@pytest.mark.parametrize(("a_value", "expected"), [(100, 100), (0, 0)])
def test_exact_boundaries_materialize_without_clamping(tmp_path, a_value, expected):
    base, engine = _world(tmp_path)
    a, b = engine.create_replica("a"), engine.create_replica("b")
    engine.apply_change(a, "a", "counters", 1, "amount", a_value, bounded_bounds=(0, 100))
    engine.apply_change(b, "b", "counters", 1, "amount", 50, bounded_bounds=(0, 100))
    result = engine.sync_replicas(a, b, str(base), "a", "b", {"counters": {"amount": POLICY}})
    assert result.flagged_for_review == 0
    assert _value(a) == _value(b) == expected


def test_sync_materializes_deltas_once_and_rejects_bound_violations_as_pending(tmp_path):
    base, engine = _world(tmp_path)
    a, b = engine.create_replica("a"), engine.create_replica("b")
    op_a = engine.apply_change(a, "a", "counters", 1, "amount", 90, bounded_bounds=(0, 100))
    op_b = engine.apply_change(b, "b", "counters", 1, "amount", 70, bounded_bounds=(0, 100))
    policies = {"counters": {"amount": POLICY}}

    result = engine.sync_replicas(a, b, str(base), "a", "b", policies)
    assert _value(a) == 90 and _value(b) == 70
    assert {item["operation_id"] for item in result.rejected_operations} == {op_a, op_b}
    assert all("BOUNDED_SUM pending" in item["reason"] for item in result.rejected_operations)
    assert result.flagged_for_review >= 1
    assert result.auto_resolved == 0
    assert all(len(_operations(path)) == 1 for path in (a, b))

    repeated = engine.sync_replicas(a, b, str(base), "a", "b", policies)
    assert _value(a) == 90 and _value(b) == 70
    assert len(_operations(a)) == len(_operations(b)) == 1
    assert repeated.rejected_operations


def test_reordered_same_source_deltas_are_not_discarded_as_obsolete(tmp_path):
    base, engine = _world(tmp_path)
    source, target = engine.create_replica("source"), engine.create_replica("target")
    first = engine.apply_change(source, "source", "counters", 1, "amount", 80,
                                bounded_bounds=(0, 100))  # +30
    second = engine.apply_change(source, "source", "counters", 1, "amount", 60,
                                 bounded_bounds=(0, 100))  # -20
    with sqlite3.connect(source) as conn:
        # _propagate_operations reads source row order; reverse it to model
        # delayed/reordered delivery of two operations from one origin.
        conn.execute("UPDATE _ss_change_log SET rowid = -rowid")
        deps = dict(conn.execute(
            "SELECT origin_id,depends_on FROM _ss_change_log WHERE origin_id IN (?, ?)",
            (first, second),
        ).fetchall())
    assert deps == {first: "[]", second: "[]"}

    result = engine.sync_replicas(
        source, target, str(base), "source", "target",
        {"counters": {"amount": POLICY}},
    )
    assert not result.rejected_operations
    assert _value(source) == _value(target) == 60
    assert {event[0] for event in _operations(target)} == {first, second}
    assert len(_operations(target)) == 2


def test_pending_deltas_retry_after_compensating_operation_makes_prefix_safe(tmp_path):
    base, engine = _world(tmp_path)
    a, b, c = (engine.create_replica(name) for name in ("a", "b", "c"))
    op_a = engine.apply_change(a, "a", "counters", 1, "amount", 90, bounded_bounds=(0, 100))
    op_b = engine.apply_change(b, "b", "counters", 1, "amount", 70, bounded_bounds=(0, 100))
    policies = {"counters": {"amount": POLICY}}
    first = engine.sync_replicas(a, b, str(base), "a", "b", policies)
    assert first.rejected_operations

    op_c = engine.apply_change(c, "c", "counters", 1, "amount", 0, bounded_bounds=(0, 100))
    restarted = CRDTSyncEngine(str(base), str(tmp_path / "replicas"))
    retry_results = []
    for left, right in ((c, a), (c, b), (b, a)):
        retry_results.append(restarted.sync_replicas(
            left, right, str(base), Path(left).stem, Path(right).stem, policies
        ))
    assert _value(a) == _value(b) == _value(c) == 60
    assert all(not result.rejected_operations for result in retry_results)
    expected_receipts = {op_a: ("a", 1, 1), op_b: ("b", 1, 1), op_c: ("c", 1, 1)}
    for replica in (a, b, c):
        with sqlite3.connect(replica) as conn:
            receipts = conn.execute(
                "SELECT origin_id,source_id,source_sequence,COUNT(*) "
                "FROM _ss_change_log WHERE bounded_delta IS NOT NULL "
                "GROUP BY origin_id,source_id,source_sequence"
            ).fetchall()
        assert {origin: (source, sequence, count) for origin, source, sequence, count in receipts} == expected_receipts


def test_direct_sql_out_of_bounds_is_not_overwritten_by_tracked_delta(tmp_path):
    base, engine = _world(tmp_path)
    a, b = engine.create_replica("a"), engine.create_replica("b")
    engine.apply_change(a, "a", "counters", 1, "amount", 60, bounded_bounds=(0, 100))
    with sqlite3.connect(b) as conn:
        conn.execute("UPDATE counters SET amount=101 WHERE id=1")
        conn.commit()
    result = engine.sync_replicas(a, b, str(base), "a", "b", {"counters": {"amount": POLICY}})
    assert _value(a) == 60 and _value(b) == 101
    assert any("outside" in item["reason"] and "101" in item["reason"] for item in result.rejected_operations)
    assert not any(item["policy"] == "UPDATE_DELIVERY" for item in result.applied_changes)


def test_bounded_sum_auto_resolution_via_api(tmp_path, monkeypatch):
    from backend.api.models import ConflictResolveRequest
    from backend.api import routes_conflicts
    from backend.api.state import app_state

    base, engine = _world(tmp_path, initial=50)
    a, b = engine.create_replica("a"), engine.create_replica("b")
    engine.apply_change(a, "a", "counters", 1, "amount", 80, bounded_bounds=(0, 100))  # +30
    engine.apply_change(b, "b", "counters", 1, "amount", 60, bounded_bounds=(0, 100))  # +10

    conflict_id = "test-auto-bounded-resolve"
    record = {
        "conflict_id": conflict_id,
        "db_id": "test_db",
        "table": "counters",
        "row_id": 1,
        "column": "amount",
        "base_value": 50,
        "value_a": 80,
        "value_b": 60,
        "replica_a_id": "a",
        "replica_b_id": "b",
        "replica_a_ts": 100.0,
        "replica_b_ts": 200.0,
        "status": "pending",
        "policy": POLICY,
    }
    stored_conflicts = {}
    monkeypatch.setattr(app_state, "get_conflict", lambda cid: record if cid == conflict_id else None)
    monkeypatch.setattr(app_state, "get_replica_path", lambda rid: str(a) if rid == "a" else str(b) if rid == "b" else None)
    monkeypatch.setattr(app_state, "get_policy", lambda db, tbl, col: POLICY)
    monkeypatch.setattr(app_state, "store_conflict", lambda cid, rec: stored_conflicts.update({cid: rec}))
    monkeypatch.setattr(routes_conflicts._manager, "apply_resolution", lambda *_: None)

    # 1. Successful auto-resolution within bounds: 50 + 30 + 10 = 90
    resp = routes_conflicts.resolve_conflict(
        ConflictResolveRequest(conflict_id=conflict_id, resolution_mode="auto")
    )
    assert resp["status"] == "resolved"
    assert resp["result"] == 90
    assert _value(a) == 90
    assert _value(b) == 90
    assert stored_conflicts[conflict_id]["status"] == "resolved"
    assert stored_conflicts[conflict_id]["resolved_value"] == 90

    # 2. Out-of-bounds auto-resolution remains flagged without mutating replicas
    record_overflow = {
        "conflict_id": "test-overflow",
        "db_id": "test_db",
        "table": "counters",
        "row_id": 1,
        "column": "amount",
        "base_value": 50,
        "value_a": 95,
        "value_b": 90,
        "replica_a_id": "a",
        "replica_b_id": "b",
        "replica_a_ts": 100.0,
        "replica_b_ts": 200.0,
        "status": "pending",
        "policy": POLICY,
    }
    monkeypatch.setattr(app_state, "get_conflict", lambda cid: record_overflow if cid == "test-overflow" else None)
    resp_overflow = routes_conflicts.resolve_conflict(
        ConflictResolveRequest(conflict_id="test-overflow", resolution_mode="auto")
    )
    assert resp_overflow["status"] == "flagged"
    assert "Unsafe overflow" in resp_overflow["explanation"]
    assert _value(a) == 90
    assert _value(b) == 90


@pytest.mark.parametrize(("trigger_sql", "reason_match"), [
    (
        "CREATE TRIGGER ignore_deliv BEFORE UPDATE OF amount ON counters "
        "BEGIN SELECT RAISE(IGNORE); END",
        "affect exactly one row",
    ),
    (
        "CREATE TRIGGER mutate_deliv AFTER UPDATE OF amount ON counters "
        "BEGIN UPDATE counters SET amount=999 WHERE id=NEW.id; END",
        "differs from the computed candidate",
    ),
])
def test_bounded_delivery_trigger_rolls_back_without_receipt(tmp_path, trigger_sql, reason_match):
    base, engine = _world(tmp_path, initial=50)
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    engine.apply_change(a, "a", "counters", 1, "amount", 80, bounded_bounds=(0, 100))  # +30

    with sqlite3.connect(b) as conn:
        conn.execute(trigger_sql)
        conn.commit()

    result = engine.sync_replicas(a, b, str(base), "a", "b", {"counters": {"amount": POLICY}})
    assert len(result.rejected_operations) == 1
    assert reason_match in result.rejected_operations[0]["reason"]
    # Target replica state remains completely unchanged
    assert _value(b) == 50
    # No receipt recorded in target replica's change log
    with sqlite3.connect(b) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM _ss_change_log WHERE replica_id='b' AND bounded_delta IS NOT NULL"
        ).fetchone()[0] == 0


def test_bounded_sum_real_affinity_rejects_lossy_integers(tmp_path):
    base = tmp_path / "base_real.db"
    initial_int = 2**53
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, amount REAL NOT NULL)")
        conn.execute("INSERT INTO counters VALUES (1, ?)", (initial_int,))
        conn.commit()
    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_real"))
    replica = engine.create_replica("r_real")

    # Storing an integer > 2**53 into a REAL column causes SQLite to convert it to IEEE 754 float,
    # losing the lowest bit. The engine's post-write validation must detect the discrepancy and roll back.
    lossy_int = 2**53 + 1
    bounds = (initial_int, initial_int + 10)
    with pytest.raises(RuntimeError, match="stored value differs"):
        engine.apply_change(replica, "r_real", "counters", 1, "amount", lossy_int, bounded_bounds=bounds)

    # State and change log must remain unchanged
    with sqlite3.connect(replica) as conn:
        row_val = conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0]
        assert row_val == float(initial_int)
        log_count = conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0]
        assert log_count == 0


def test_three_way_large_integer_divergence(tmp_path):
    # Concurrent independent mutations above 2**53
    base_val = 2**53 + 10
    base = tmp_path / "base_large.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES (1, ?)", (base_val,))
        conn.commit()

    engine = CRDTSyncEngine(str(base), str(tmp_path / "replicas_large"))
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    min_b = 2**53
    max_b = 2**53 + 40
    bounds = (min_b, max_b)
    policy_str = f"BOUNDED_SUM[min={min_b},max={max_b}]"
    policies = {"counters": {"amount": policy_str}}

    # 1. Safe concurrent convergence: A adds 5, B adds 8 => candidate = base + 5 + 8 = base + 13
    engine.apply_change(a, "a", "counters", 1, "amount", base_val + 5, bounded_bounds=bounds)
    engine.apply_change(b, "b", "counters", 1, "amount", base_val + 8, bounded_bounds=bounds)

    result = engine.sync_replicas(a, b, str(base), "a", "b", policies)
    expected_sum = base_val + 13
    assert not result.rejected_operations
    assert result.flagged_for_review == 0
    with sqlite3.connect(a) as conn:
        val_a = conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0]
    with sqlite3.connect(b) as conn:
        val_b = conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0]
    assert val_a == val_b == expected_sum
    assert isinstance(val_a, int)
    assert val_a > 2**53

    # 2. Out-of-bounds concurrent divergence: candidate exceeds max_b
    a2 = engine.create_replica("a2")
    b2 = engine.create_replica("b2")
    op_a2 = engine.apply_change(a2, "a2", "counters", 1, "amount", base_val + 15, bounded_bounds=bounds)
    op_b2 = engine.apply_change(b2, "b2", "counters", 1, "amount", base_val + 20, bounded_bounds=bounds)

    result_overflow = engine.sync_replicas(a2, b2, str(base), "a2", "b2", policies)
    assert result_overflow.flagged_for_review >= 1
    # Check operation identities and reasons in rejected_operations
    assert {op["operation_id"] for op in result_overflow.rejected_operations} == {op_a2, op_b2}
    assert all("BOUNDED_SUM pending" in op["reason"] for op in result_overflow.rejected_operations)

    # State and receipts remain unchanged on both replicas
    with sqlite3.connect(a2) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == base_val + 15
        receipts_a2 = conn.execute(
            "SELECT origin_id, COUNT(*) FROM _ss_change_log WHERE bounded_delta IS NOT NULL GROUP BY origin_id"
        ).fetchall()
        assert receipts_a2 == [(op_a2, 1)]
    with sqlite3.connect(b2) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == base_val + 20
        receipts_b2 = conn.execute(
            "SELECT origin_id, COUNT(*) FROM _ss_change_log WHERE bounded_delta IS NOT NULL GROUP BY origin_id"
        ).fetchall()
        assert receipts_b2 == [(op_b2, 1)]

    # Repeated sync is idempotent and does not create duplicate receipts
    result_repeat = engine.sync_replicas(a2, b2, str(base), "a2", "b2", policies)
    assert {op["operation_id"] for op in result_repeat.rejected_operations} == {op_a2, op_b2}
    with sqlite3.connect(a2) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE bounded_delta IS NOT NULL").fetchone()[0] == 1
    with sqlite3.connect(b2) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE bounded_delta IS NOT NULL").fetchone()[0] == 1


def test_bounded_resolve_relay_rejects_missing_bounds(tmp_path):
    base, engine = _world(tmp_path, initial=50)
    a, b, c = engine.create_replica("a"), engine.create_replica("b"), engine.create_replica("c")
    policies = {"counters": {"amount": POLICY}}
    op_a = engine.apply_change(a, "a", "counters", 1, "amount", 70, bounded_bounds=(0, 100))
    op_b = engine.apply_change(b, "b", "counters", 1, "amount", 60, bounded_bounds=(0, 100))

    # Replicate prior operation op_a to c so c matches expected prior state (70)
    engine.sync_replicas(a, c, str(base), "a", "c", policies)
    assert _value(c) == 70

    import json
    import uuid
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    resolve_id = str(uuid.uuid4())
    payload = {"kind": "cell", "column": "amount", "value": 80}  # No "bounds" key!
    with sqlite3.connect(a) as conn:
        conn.execute(
            """INSERT INTO _ss_change_log
            (id, table_name, row_id, column_name, old_value, new_value,
             ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence,
             source_id, source_sequence, depends_on)
            VALUES (?, 'counters', '1', '*', ?, ?, 100.0, 1, 'a', ?, 'RESOLVE', ?, 10, 'resolution:a:b', 1, ?)""",
            (str(uuid.uuid4()), json.dumps({"a": {"id": 1, "amount": 70}}), json.dumps(payload),
             now_iso, resolve_id, json.dumps([op_a, op_b])),
        )
        conn.commit()

    result = engine.sync_replicas(a, c, str(base), "a", "c", policies)
    assert any("requires bounds metadata" in op.get("reason", "") for op in result.rejected_operations)
    # Target replica c remains unchanged at 70 and records zero receipt for the invalid resolve
    assert _value(c) == 70
    with sqlite3.connect(c) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (resolve_id,)).fetchone()[0] == 0


def test_bounded_resolve_relay_rejects_mismatched_bounds(tmp_path):
    base, engine = _world(tmp_path, initial=50)
    a, b, c = engine.create_replica("a"), engine.create_replica("b"), engine.create_replica("c")
    policies = {"counters": {"amount": POLICY}}
    op_a = engine.apply_change(a, "a", "counters", 1, "amount", 70, bounded_bounds=(0, 100))
    op_b = engine.apply_change(b, "b", "counters", 1, "amount", 60, bounded_bounds=(0, 100))

    # Replicate prior operation op_a to c so c matches expected prior state (70)
    engine.sync_replicas(a, c, str(base), "a", "c", policies)
    assert _value(c) == 70

    import json
    import uuid
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    resolve_id = str(uuid.uuid4())
    payload = {"kind": "cell", "column": "amount", "value": 40, "bounds": {"min": 10, "max": 50}}
    with sqlite3.connect(a) as conn:
        conn.execute(
            """INSERT INTO _ss_change_log
            (id, table_name, row_id, column_name, old_value, new_value,
             ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence,
             source_id, source_sequence, depends_on)
            VALUES (?, 'counters', '1', '*', ?, ?, 100.0, 1, 'a', ?, 'RESOLVE', ?, 10, 'resolution:a:b', 1, ?)""",
            (str(uuid.uuid4()), json.dumps({"a": {"id": 1, "amount": 70}}), json.dumps(payload),
             now_iso, resolve_id, json.dumps([op_a, op_b])),
        )
        conn.commit()

    result = engine.sync_replicas(a, c, str(base), "a", "c", policies)
    assert any("do not match policy bounds" in op.get("reason", "") for op in result.rejected_operations)
    # Target replica c remains unchanged at 70 and records zero receipt for the invalid resolve
    assert _value(c) == 70
    with sqlite3.connect(c) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (resolve_id,)).fetchone()[0] == 0


def test_valid_bounded_resolution_relay_is_idempotent(tmp_path):
    import json
    import uuid
    from datetime import datetime, timezone

    base, engine = _world(tmp_path, initial=50)
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    policies = {"counters": {"amount": POLICY}}
    op_a = engine.apply_change(a, "a", "counters", 1, "amount", 70, bounded_bounds=(0, 100))

    # A valid bounded RESOLVE entry recorded on replica a
    now_iso = datetime.now(timezone.utc).isoformat()
    resolve_id = str(uuid.uuid4())
    payload = {"kind": "cell", "column": "amount", "value": 80, "bounds": {"min": 0, "max": 100}}
    with sqlite3.connect(a) as conn:
        conn.execute(
            """INSERT INTO _ss_change_log
            (id, table_name, row_id, column_name, old_value, new_value,
             ts_pt, ts_l, replica_id, applied_at, op_type, origin_id, sequence,
             source_id, source_sequence, depends_on, bounded_delta, bounds_min, bounds_max)
            VALUES (?, 'counters', '1', '*', ?, ?, 100.0, 1, 'a', ?, 'RESOLVE', ?, 10, 'resolution:a:b', 1, ?, NULL, 0, 100)""",
            (str(uuid.uuid4()), json.dumps({"a": {"id": 1, "amount": 70}}), json.dumps(payload),
             now_iso, resolve_id, json.dumps([op_a])),
        )
        conn.commit()

    # First relay delivery from a to b
    delivered1, rejected1 = engine._propagate_operations((a, "a"), (b, "b"), policies=policies)
    assert not rejected1
    assert any(item["operation_id"] == resolve_id for item in delivered1)
    assert _value(b) == 80
    with sqlite3.connect(b) as conn:
        receipts = conn.execute(
            "SELECT origin_id, bounds_min, bounds_max FROM _ss_change_log WHERE origin_id=?",
            (resolve_id,),
        ).fetchall()
        assert len(receipts) == 1
        assert receipts[0][1] == 0 and receipts[0][2] == 100

    # Second relay delivery from a to b (identical bounded resolution re-delivered)
    delivered2, rejected2 = engine._propagate_operations((a, "a"), (b, "b"), policies=policies)
    assert not rejected2
    assert not any(item["operation_id"] == resolve_id for item in delivered2)
    # State remains 80, exactly one receipt remains, and no rejection
    assert _value(b) == 80
    with sqlite3.connect(b) as conn:
        receipts_after = conn.execute(
            "SELECT origin_id, bounds_min, bounds_max FROM _ss_change_log WHERE origin_id=?",
            (resolve_id,),
        ).fetchall()
        assert len(receipts_after) == 1
        assert receipts_after[0][1] == 0 and receipts_after[0][2] == 100



\n