"""Reproducible generated properties and adversarial write regressions.

The generated inputs use fixed seeds so failures reproduce without an added
runtime/test dependency. These tests establish only the stated properties.
APPEND's pairwise stable-ID ordering is checked for commutativity; identical
input deduplication is narrow and does not assert associativity or N-way
idempotence after materialized strings lose their contribution identities.
"""

from __future__ import annotations

import random
import sqlite3

import pytest

import backend.engine.crdt_sync as crdt_sync
from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.policy_registry import PolicyType
from backend.engine.semantic_resolver import ResolutionError, SemanticResolver


def _resolve(policy, base=None, a=None, b=None, **kwargs):
    return SemanticResolver.resolve(
        policy=policy, base_value=base, replica_a_value=a, replica_b_value=b, **kwargs
    )


def test_generated_policy_commutativity_for_valid_domains():
    rng = random.Random(0x5E6A_71C)
    for _ in range(250):
        base = rng.randint(-10_000, 10_000)
        a = rng.randint(-10_000, 10_000)
        b = rng.randint(-10_000, 10_000)
        for policy in (PolicyType.SUM, PolicyType.MIN, PolicyType.MAX):
            forward = _resolve(policy, base, a, b)
            reverse = _resolve(policy, base, b, a)
            assert (forward.status, forward.resolved_value) == (reverse.status, reverse.resolved_value)

        af, bf = rng.uniform(-1e6, 1e6), rng.uniform(-1e6, 1e6)
        assert _resolve("AVG", base, af, bf).resolved_value == _resolve("AVG", base, bf, af).resolved_value

        left_text = rng.choice(["", "café；東京", "line\n二", "🧪;data", "plain"])
        right_text = rng.choice(["", "naïve；x", "λ→β", "🧬", "plain"])
        append_ab = _resolve(
            "APPEND", "ancestor", left_text, right_text,
            replica_a_id="replica-a", replica_b_id="replica-b",
        )
        append_ba = _resolve(
            "APPEND", "ancestor", right_text, left_text,
            replica_a_id="replica-b", replica_b_id="replica-a",
        )
        assert append_ab.resolved_value == append_ba.resolved_value

        ts_a, ts_b = rng.randint(0, 100), rng.randint(0, 100)
        lww_ab = _resolve(
            "LWW", a=a, b=b, replica_a_id="replica-a", replica_b_id="replica-b",
            replica_a_ts=ts_a, replica_b_ts=ts_b,
        )
        lww_ba = _resolve(
            "LWW", a=b, b=a, replica_a_id="replica-b", replica_b_id="replica-a",
            replica_a_ts=ts_b, replica_b_ts=ts_a,
        )
        assert lww_ab.resolved_value == lww_ba.resolved_value

        reject_ab = _resolve("REJECT", base, a, b)
        reject_ba = _resolve("REJECT", base, b, a)
        assert reject_ab.status == reject_ba.status == "flagged"
        assert reject_ab.resolved_value is reject_ba.resolved_value is None


def test_generated_valid_associativity_and_idempotence_boundaries():
    rng = random.Random(0xA550_C1A7)
    for _ in range(200):
        base, a, b, c = (rng.randint(-100_000, 100_000) for _ in range(4))
        sum_ab = _resolve("SUM", base, a, b).resolved_value
        sum_left = _resolve("SUM", base, sum_ab, c).resolved_value
        sum_bc = _resolve("SUM", base, b, c).resolved_value
        sum_right = _resolve("SUM", base, a, sum_bc).resolved_value
        assert sum_left == sum_right  # associative only with this fixed common ancestor
        assert _resolve("SUM", base, a, a).resolved_value == 2 * a - base
        if a != base:
            assert _resolve("SUM", base, a, a).resolved_value != a

        min_ab = _resolve("MIN", base, a, b).resolved_value
        min_bc = _resolve("MIN", base, b, c).resolved_value
        max_ab = _resolve("MAX", base, a, b).resolved_value
        max_bc = _resolve("MAX", base, b, c).resolved_value
        assert _resolve("MIN", base, min_ab, c).resolved_value == _resolve(
            "MIN", base, a, min_bc
        ).resolved_value
        assert _resolve("MAX", base, max_ab, c).resolved_value == _resolve(
            "MAX", base, a, max_bc
        ).resolved_value
        assert _resolve("MIN", base, a, a).resolved_value == a
        assert _resolve("MAX", base, a, a).resolved_value == a


def test_avg_non_associativity_is_explicit():
    a, b, c = 10.0, 20.0, 40.0
    ab = _resolve("AVG", a=a, b=b).resolved_value
    bc = _resolve("AVG", a=b, b=c).resolved_value
    assert _resolve("AVG", a=ab, b=c).resolved_value == 27.5
    assert _resolve("AVG", a=a, b=bc).resolved_value == 20.0
    assert _resolve("AVG", a=42.0, b=42.0).resolved_value == 42.0


def test_append_empty_unicode_none_and_identical_inputs():
    assert _resolve("APPEND", "", "", "").resolved_value == ""
    assert _resolve("APPEND", None, None, "新しい；項目").resolved_value == "新しい；項目"
    result = _resolve(
        "APPEND", "基準", "café；one", "λ→two",
        replica_a_id="a", replica_b_id="b",
    )
    assert result.resolved_value == "café；one; λ→two"
    assert _resolve("APPEND", "base", "identical", "identical").resolved_value == "identical"


def test_append_repeat_sync_does_not_duplicate_delivery(tmp_path):
    base = tmp_path / "append_base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.execute("INSERT INTO notes VALUES (1, 'ancestor')")
    engine = CRDTSyncEngine(str(base), str(tmp_path))
    a = engine.create_replica("append_a")
    b = engine.create_replica("append_b")
    engine.apply_change(a, "append_a", "notes", 1, "body", "café；a")
    engine.apply_change(b, "append_b", "notes", 1, "body", "λ→b")

    first = engine.sync_replicas(a, b, str(base), "append_a", "append_b", {"notes": {"body": "APPEND"}})
    assert first.auto_resolved == 1
    with sqlite3.connect(a) as ca, sqlite3.connect(b) as cb:
        expected = "café；a; λ→b"
        assert ca.execute("SELECT body FROM notes WHERE id=1").fetchone() == (expected,)
        assert cb.execute("SELECT body FROM notes WHERE id=1").fetchone() == (expected,)
    second = engine.sync_replicas(a, b, str(base), "append_a", "append_b", {"notes": {"body": "APPEND"}})
    assert second.total_conflicts == second.auto_resolved == 0
    with sqlite3.connect(a) as conn:
        assert conn.execute("SELECT body FROM notes WHERE id=1").fetchone() == (expected,)


@pytest.mark.parametrize(
    "policy,base,a,b",
    [
        ("SUM", 0, object(), 2),
        ("AVG", None, "not numeric", 1),
        ("MIN", None, "text", 1),
        ("UNKNOWN_POLICY", None, 1, 2),
    ],
)
def test_invalid_policy_inputs_raise_resolution_error(policy, base, a, b):
    with pytest.raises(ResolutionError):
        _resolve(policy, base, a, b)


def _new_engine(tmp_path):
    base = tmp_path / "writes_base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'original')")
    engine = CRDTSyncEngine(str(base), str(tmp_path))
    return base, engine, engine.create_replica("writes_replica")


def test_invalid_tracked_update_and_triggered_insert_roll_back_data_and_log(tmp_path):
    _, engine, replica = _new_engine(tmp_path)
    with sqlite3.connect(replica) as conn:
        conn.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON items BEGIN SELECT RAISE(ABORT, 'rejected'); END")
    with sqlite3.connect(replica) as conn:
        before_log_count = conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0]
    with pytest.raises(sqlite3.OperationalError):
        engine.apply_change(replica, "writes_replica", "items", 1, "missing_column", "bad")
    with pytest.raises(sqlite3.IntegrityError, match="rejected"):
        engine.apply_insert(replica, "writes_replica", "items", {"id": 2, "value": "bad"})
    with sqlite3.connect(replica) as conn:
        assert conn.execute("SELECT * FROM items ORDER BY id").fetchall() == [(1, "original")]
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == before_log_count


@pytest.mark.parametrize("operation", ["update", "insert", "delete"])
def test_tracked_mutations_begin_immediate_before_table_access(tmp_path, monkeypatch, operation):
    _, engine, replica = _new_engine(tmp_path)
    statements = []
    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(crdt_sync.sqlite3, "connect", traced_connect)
    if operation == "update":
        engine.apply_change(replica, "writes_replica", "items", 1, "value", "updated")
        expected_sql = 'SELECT "value" FROM "items"'
    elif operation == "insert":
        engine.apply_insert(replica, "writes_replica", "items", {"id": 2, "value": "inserted"})
        expected_sql = 'INSERT INTO "items"'
    else:
        engine.apply_delete(replica, "writes_replica", "items", 1)
        expected_sql = 'SELECT * FROM "items"'

    normalized = [sql.strip().upper() for sql in statements]
    begin_index = next(i for i, sql in enumerate(normalized) if sql == "BEGIN IMMEDIATE")
    table_access = expected_sql.upper()
    access_index = next(i for i, sql in enumerate(normalized) if table_access in sql)
    assert begin_index < access_index
