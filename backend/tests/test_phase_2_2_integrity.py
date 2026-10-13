"""Focused integrity regressions for Phase 2.2 hardening."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.api import routes_conflicts, routes_sync
from backend.api.models import ConflictResolveRequest, SyncRequest
from backend.engine.crdt_sync import CRDTSyncEngine, SyncResult, _CHANGE_LOG_DDL, _ensure_change_log_table
from backend.engine.conflict_detector import ConflictInfo, DetectResult


def _database(path: Path, *, composite: bool = False) -> None:
    with sqlite3.connect(path) as conn:
        if composite:
            conn.execute(
                "CREATE TABLE items (a INTEGER, b INTEGER, value TEXT, PRIMARY KEY (a, b))"
            )
            conn.execute("INSERT INTO items VALUES (1, 1, 'first')")
            conn.execute("INSERT INTO items VALUES (1, 2, 'second')")
        else:
            conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO items VALUES (1, 'old')")
        conn.commit()


def _read(path: Path, query: str, params=()):
    with sqlite3.connect(path) as conn:
        return conn.execute(query, params).fetchall()


def test_legacy_change_log_schema_is_backfilled_once_on_upgrade(tmp_path):
    db = tmp_path / "legacy-log.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE _ss_change_log (id TEXT PRIMARY KEY, table_name TEXT, row_id TEXT, column_name TEXT, old_value TEXT, new_value TEXT, ts_pt REAL, ts_l INTEGER, replica_id TEXT, applied_at TEXT)")
        conn.execute("INSERT INTO _ss_change_log VALUES ('op-1','items','1','value','old','new',1,0,'replica-a','now')")
        _ensure_change_log_table(conn)
        row = conn.execute("SELECT origin_id,sequence,source_id,source_sequence FROM _ss_change_log WHERE id='op-1'").fetchone()
        assert row == ("op-1", 1, "replica-a", 1)
        indexes = {r[1] for r in conn.execute("PRAGMA index_list('_ss_change_log')")}
        assert {"_ss_change_log_sequence_idx", "_ss_change_log_origin_idx", "_ss_change_log_source_row_idx"} <= indexes


@pytest.fixture
def replica_set(tmp_path: Path):
    base = tmp_path / "base.db"
    _database(base)
    engine = CRDTSyncEngine(str(base), str(tmp_path))
    return tmp_path, base, engine


def test_delete_followed_by_reinsert_propagates_new_row_after_restart(replica_set):
    directory, base, engine = replica_set
    replica_a = Path(engine.create_replica("reinsert_a"))
    replica_b = Path(engine.create_replica("reinsert_b"))

    engine.apply_delete(str(replica_a), "reinsert_a", "items", 1)
    engine.apply_insert(str(replica_a), "reinsert_a", "items", {"id": 1, "value": "new"})
    with sqlite3.connect(replica_a) as conn:
        conn.execute("VACUUM")
    engine = CRDTSyncEngine(str(base), str(directory))
    result = engine.sync_replicas(
        str(replica_a), str(replica_b), str(base), "reinsert_a", "reinsert_b", {}
    )

    assert _read(replica_b, "SELECT value FROM items WHERE id=1") == [("new",)]
    assert any(row["policy"] == "INSERT_DELIVERY" for row in result.applied_changes)


def test_insert_update_propagate_three_replicas_in_reverse_pair_order(replica_set):
    directory, base, engine = replica_set
    a = Path(engine.create_replica("ops_a"))
    b = Path(engine.create_replica("ops_b"))
    c = Path(engine.create_replica("ops_c"))
    engine.apply_change(str(a), "ops_a", "items", 1, "value", "updated")
    engine.sync_replicas(str(b), str(a), str(base), "ops_b", "ops_a", {})
    restarted = CRDTSyncEngine(str(base), str(directory))
    restarted.sync_replicas(str(c), str(b), str(base), "ops_c", "ops_b", {})
    assert _read(c, "SELECT value FROM items WHERE id=1") == [("updated",)]
    restarted.apply_insert(str(a), "ops_a", "items", {"id": 2, "value": "inserted"})
    restarted.sync_replicas(str(b), str(a), str(base), "ops_b", "ops_a", {})
    restarted.sync_replicas(str(c), str(b), str(base), "ops_c", "ops_b", {})
    assert _read(c, "SELECT value FROM items WHERE id=2") == [("inserted",)]


def test_duplicate_operation_delivery_is_idempotent_and_keeps_concurrent_edit(replica_set):
    directory, base, engine = replica_set
    a = Path(engine.create_replica("dup_a"))
    b = Path(engine.create_replica("dup_b"))
    engine.apply_change(str(a), "dup_a", "items", 1, "value", "from-a")
    engine.sync_replicas(str(a), str(b), str(base), "dup_a", "dup_b", {})
    first_count = _read(b, "SELECT COUNT(*) FROM _ss_change_log WHERE source_id='dup_a'")[0][0]
    engine.sync_replicas(str(a), str(b), str(base), "dup_a", "dup_b", {})
    assert _read(b, "SELECT COUNT(*) FROM _ss_change_log WHERE source_id='dup_a'")[0][0] == first_count
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("from-a",)]

    engine.apply_change(str(a), "dup_a", "items", 1, "value", "later-a")
    engine.apply_change(str(b), "dup_b", "items", 1, "value", "local-b")
    conflict_result = engine.sync_replicas(str(a), str(b), str(base), "dup_a", "dup_b", {})
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("local-b",)]
    assert conflict_result.total_conflicts == 1
    assert conflict_result.flagged_for_review == 1


def test_delayed_old_delete_cannot_override_newer_insert(replica_set):
    _, _, engine = replica_set
    target = Path(engine.create_replica("delay_target"))
    status, _ = engine._apply_received_operation(
        str(target), "delay_target", "items", "2", "*", None,
        json.dumps({"id": 2, "value": "reinserted"}), "INSERT", "op-new", "source-a", 2, 2.0, 0, {"op-new", "op-old"},
    )
    assert status == "applied"
    status, _ = engine._apply_received_operation(
        str(target), "delay_target", "items", "2", "*",
        json.dumps({"id": 2, "value": "reinserted"}), None, "DELETE", "op-old", "source-a", 1, 1.0, 0, {"op-new", "op-old"},
    )
    assert status == "obsolete"
    assert _read(target, "SELECT value FROM items WHERE id=2") == [("reinserted",)]


@pytest.mark.parametrize("trigger_sql", [
    "CREATE TRIGGER ignore_insert BEFORE INSERT ON items WHEN NEW.id=2 BEGIN SELECT RAISE(IGNORE); END",
    "CREATE TRIGGER mutate_insert AFTER INSERT ON items WHEN NEW.id=2 BEGIN UPDATE items SET value='mutated' WHERE id=NEW.id; END",
])
def test_insert_delivery_trigger_mismatch_rolls_back_without_receipt(replica_set, trigger_sql):
    _, _, engine = replica_set
    target = Path(engine.create_replica("insert_trigger_target"))
    with sqlite3.connect(target) as conn:
        conn.execute(trigger_sql)
    status, reason = engine._apply_received_operation(
        str(target), "insert_trigger_target", "items", "2", "*", None,
        json.dumps({"id": 2, "value": "requested"}), "INSERT", "insert-op",
        "insert-source", 1, 1.0, 0, {"insert-op"},
    )
    assert status == "rejected"
    assert "stored INSERT row" in reason
    assert _read(target, "SELECT * FROM items WHERE id=2") == []
    assert _read(target, "SELECT * FROM _ss_change_log WHERE origin_id='insert-op'") == []


@pytest.mark.parametrize("first_peer", ["resolve_a", "resolve_b"])
@pytest.mark.parametrize("writer", ["engine", "api"])
def test_resolution_operation_relays_to_third_replica_in_either_peer_order(replica_set, first_peer, writer):
    directory, base, engine = replica_set
    a = Path(engine.create_replica("resolve_a"))
    b = Path(engine.create_replica("resolve_b"))
    c = Path(engine.create_replica("resolve_c"))
    a_op = engine.apply_change(str(a), "resolve_a", "items", 1, "value", "from-a")
    b_op = engine.apply_change(str(b), "resolve_b", "items", 1, "value", "from-b")
    if writer == "engine":
        engine._write_resolved_pair(
            str(a), "resolve_a", str(b), "resolve_b", "items", 1,
            "value", "chosen", "update",
        )
    else:
        routes_conflicts._write_resolution_atomically(
            str(a), str(b), "items", 1, "value", "chosen", "resolve_a", "resolve_b"
        )

    a_resolution = _read(a, "SELECT origin_id,source_id,source_sequence,depends_on FROM _ss_change_log WHERE op_type='RESOLVE'")
    b_resolution = _read(b, "SELECT origin_id,source_id,source_sequence,depends_on FROM _ss_change_log WHERE op_type='RESOLVE'")
    assert a_resolution == b_resolution
    assert a_resolution[0][3] == json.dumps(sorted([a_op, b_op]))
    assert a_resolution[0][2] > 0

    first = a if first_peer == "resolve_a" else b
    second = b if first_peer == "resolve_a" else a
    first_id = first_peer
    second_id = "resolve_b" if first_peer == "resolve_a" else "resolve_a"
    engine.sync_replicas(str(first), str(c), str(base), first_id, "resolve_c", {})
    engine.sync_replicas(str(second), str(c), str(base), second_id, "resolve_c", {})
    assert _read(c, "SELECT value FROM items WHERE id=1") == [("chosen",)]
    c_resolution = _read(
        c,
        "SELECT origin_id,source_id,source_sequence,depends_on FROM _ss_change_log WHERE op_type='RESOLVE'",
    )
    assert c_resolution == a_resolution
    assert _read(c, "SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (a_resolution[0][0],)) == [(1,)]


def test_partial_operation_delivery_surfaces_failure_and_retry_is_idempotent(tmp_path):
    base = tmp_path / "partial_base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)")
        conn.executemany("INSERT INTO items VALUES (?, ?)", [(1, "one"), (2, "two")])
    engine = CRDTSyncEngine(str(base), str(tmp_path))
    a = Path(engine.create_replica("partial_a"))
    b = Path(engine.create_replica("partial_b"))
    first_id = engine.apply_change(str(a), "partial_a", "items", 1, "value", "one-new")
    second_id = engine.apply_change(str(a), "partial_a", "items", 2, "value", "two-new")
    with sqlite3.connect(b) as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE UPDATE ON items WHEN OLD.id=2 BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        engine.sync_replicas(str(a), str(b), str(base), "partial_a", "partial_b", {})
    # Delivery is now a single receiver transaction with per-operation
    # savepoints: a raised write failure rolls back all operations in the
    # batch, including the first row and its receipt.
    assert _read(b, "SELECT value FROM items ORDER BY id") == [("one",), ("two",)]
    assert _read(b, "SELECT COUNT(*) FROM _ss_change_log WHERE source_id='partial_a'") == [(0,)]
    with sqlite3.connect(b) as conn:
        conn.execute("DROP TRIGGER fail_second")
    retry = engine.sync_replicas(str(a), str(b), str(base), "partial_a", "partial_b", {})
    assert _read(b, "SELECT value FROM items ORDER BY id") == [("one-new",), ("two-new",)]
    assert _read(b, "SELECT COUNT(*) FROM _ss_change_log WHERE source_id='partial_a'") == [(2,)]
    assert dict(_read(b, "SELECT origin_id,COUNT(*) FROM _ss_change_log WHERE origin_id IN (?,?) GROUP BY origin_id", (first_id, second_id))) == {first_id: 1, second_id: 1}
    assert any(op["operation_id"] == first_id for op in retry.applied_changes)
    assert any(op["operation_id"] == second_id for op in retry.applied_changes)


@pytest.mark.parametrize("bad_payload", [None, "not-a-row"])
def test_update_resurrects_invalid_payload_stays_unresolved_without_writes(replica_set, monkeypatch, bad_payload):
    _, base, engine = replica_set
    a = Path(engine.create_replica("invalid_resurrect_a"))
    b = Path(engine.create_replica("invalid_resurrect_b"))
    conflict = ConflictInfo(
        conflict_id="invalid-resurrect", table="items", row_id=1, column="*",
        base_value={"id": 1, "value": "old"}, replica_a_value=bad_payload,
        replica_b_value=None, replica_a_id="invalid_resurrect_a", replica_b_id="invalid_resurrect_b",
        replica_a_ts=1.0, replica_b_ts=2.0, detected_at="test", conflict_type="UPDATE_DELETE",
    )
    monkeypatch.setattr(engine._detector, "detect", lambda **_: DetectResult([conflict], []))
    recorded = []
    monkeypatch.setattr(engine._manager, "add_conflict", lambda item: recorded.append(item.conflict_id))
    before_rows = (_read(a, "SELECT * FROM items"), _read(b, "SELECT * FROM items"))
    before_logs = (_read(a, "SELECT COUNT(*) FROM _ss_change_log"), _read(b, "SELECT COUNT(*) FROM _ss_change_log"))

    result = engine.sync_replicas(
        str(a), str(b), str(base), "invalid_resurrect_a", "invalid_resurrect_b",
        {"items": {"__tombstone__": "UPDATE_RESURRECTS"}},
    )

    assert result.auto_resolved == 0
    assert result.flagged_for_review == 1
    assert result.applied_changes == []
    assert result.flagged_conflicts == ["invalid-resurrect"]
    assert recorded == ["invalid-resurrect"]
    assert (_read(a, "SELECT * FROM items"), _read(b, "SELECT * FROM items")) == before_rows
    assert (_read(a, "SELECT COUNT(*) FROM _ss_change_log"), _read(b, "SELECT COUNT(*) FROM _ss_change_log")) == before_logs


def test_tombstone_relays_a_to_b_to_c_across_engine_restart_and_is_idempotent(replica_set):
    directory, base, engine = replica_set
    a = Path(engine.create_replica("chain_a"))
    b = Path(engine.create_replica("chain_b"))
    c = Path(engine.create_replica("chain_c"))
    engine.apply_delete(str(a), "chain_a", "items", 1)
    engine.sync_replicas(str(a), str(b), str(base), "chain_a", "chain_b", {})

    restarted = CRDTSyncEngine(str(base), str(directory))
    first = restarted.sync_replicas(str(b), str(c), str(base), "chain_b", "chain_c", {})
    assert _read(c, "SELECT * FROM items") == []
    assert any(change["policy"] == "DELETE_DELIVERY" for change in first.applied_changes)
    before = _read(c, "SELECT COUNT(*) FROM _ss_change_log WHERE origin_id IS NOT NULL")
    restarted.sync_replicas(str(b), str(c), str(base), "chain_b", "chain_c", {})
    assert _read(c, "SELECT COUNT(*) FROM _ss_change_log WHERE origin_id IS NOT NULL") == before


def test_tombstone_relays_c_to_b_to_a(replica_set):
    _, base, engine = replica_set
    c = Path(engine.create_replica("reverse_c"))
    b = Path(engine.create_replica("reverse_b"))
    a = Path(engine.create_replica("reverse_a"))
    engine.apply_delete(str(c), "reverse_c", "items", 1)
    engine.sync_replicas(str(c), str(b), str(base), "reverse_c", "reverse_b", {})
    engine.sync_replicas(str(b), str(a), str(base), "reverse_b", "reverse_a", {})
    assert _read(a, "SELECT * FROM items") == []
    assert _read(b, "SELECT * FROM items") == []


def test_composite_pk_is_skipped_and_never_mutated_by_tombstone_delivery(tmp_path):
    base = tmp_path / "composite_base.db"
    _database(base, composite=True)
    engine = CRDTSyncEngine(str(base), str(tmp_path))
    a = Path(engine.create_replica("composite_a"))
    b = Path(engine.create_replica("composite_b"))
    with sqlite3.connect(a) as conn:
        conn.execute(
            "INSERT INTO _ss_change_log "
            "(id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,applied_at,op_type) "
            "VALUES ('old-delete','items','1','*',? ,NULL,1,0,'composite_a','now','DELETE')",
            (json.dumps({"a": 1, "b": 1, "value": "first"}),),
        )
        conn.commit()

    result = engine.sync_replicas(str(a), str(b), str(base), "composite_a", "composite_b", {})
    assert "items" in result.skipped_tables
    assert _read(b, "SELECT * FROM items ORDER BY b") == [(1, 1, "first"), (1, 2, "second")]
    with pytest.raises(RuntimeError, match="single-column primary key"):
        engine.apply_delete(str(b), "composite_b", "items", 1)


def test_received_tombstone_delete_and_log_are_atomic(tmp_path):
    target = tmp_path / "atomic.db"
    _database(target)
    with sqlite3.connect(target) as conn:
        conn.execute(_CHANGE_LOG_DDL)
        conn.execute(
            "CREATE TRIGGER fail_delete_log BEFORE INSERT ON _ss_change_log "
            "WHEN NEW.op_type = 'DELETE' BEGIN SELECT RAISE(ABORT, 'injected log failure'); END"
        )
        conn.commit()
    engine = CRDTSyncEngine()

    with pytest.raises(sqlite3.IntegrityError, match="injected log failure"):
        engine._apply_received_tombstone(
            str(target), "target", "items", "1", {"id": 1, "value": "old"}, "origin-1"
        )
    assert _read(target, "SELECT * FROM items") == [(1, "old")]


def test_tombstone_validation_rechecks_after_concurrent_writer_commits(tmp_path):
    target = tmp_path / "race.db"
    _database(target)
    with sqlite3.connect(target) as conn:
        conn.execute(_CHANGE_LOG_DDL)
        conn.commit()
    engine = CRDTSyncEngine()
    started = threading.Event()
    result: list[bool] = []

    with sqlite3.connect(target, timeout=2) as lock_conn:
        lock_conn.execute("BEGIN IMMEDIATE")

        def deliver():
            started.set()
            result.append(engine._apply_received_tombstone(
                str(target), "target", "items", "1", {"id": 1, "value": "old"}, "origin-race"
            ))

        worker = threading.Thread(target=deliver)
        worker.start()
        assert started.wait(1)
        lock_conn.execute("UPDATE items SET value='local' WHERE id=1")
        lock_conn.execute(
            "INSERT INTO _ss_change_log "
            "(id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,applied_at,op_type,origin_id) "
            "VALUES ('local-op','items','1','value','old','local',1,0,'target','now','UPDATE','local-op')"
        )
        lock_conn.commit()
    worker.join(3)
    assert not worker.is_alive()
    assert result == [False]
    assert _read(target, "SELECT value FROM items WHERE id=1") == [("local",)]


def _make_replica_pair(tmp_path: Path, *, trigger_b: bool = False):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    _database(a)
    _database(b)
    if trigger_b:
        with sqlite3.connect(b) as conn:
            conn.execute(
                "CREATE TRIGGER fail_update BEFORE UPDATE ON items "
                "BEGIN SELECT RAISE(ABORT, 'injected update failure'); END"
            )
            conn.commit()
    return a, b


def test_null_row_resolution_deletes_both_replicas(tmp_path):
    a, b = _make_replica_pair(tmp_path)
    routes_conflicts._write_resolution_atomically(str(a), str(b), "items", 1, "*", None)
    assert _read(a, "SELECT * FROM items") == []
    assert _read(b, "SELECT * FROM items") == []


def test_ignored_delete_trigger_prevents_false_resolved_success(tmp_path):
    a, b = _make_replica_pair(tmp_path)
    with sqlite3.connect(b) as conn:
        conn.execute(
            "CREATE TRIGGER ignore_delete BEFORE DELETE ON items "
            "BEGIN SELECT RAISE(IGNORE); END"
        )
        conn.commit()
    with pytest.raises(HTTPException, match="did not remove row"):
        routes_conflicts._write_resolution_atomically(str(a), str(b), "items", 1, "*", None)
    assert _read(a, "SELECT * FROM items") == [(1, "old")]
    assert _read(b, "SELECT * FROM items") == [(1, "old")]


def test_wal_replica_is_rejected_before_resolution_writes(tmp_path):
    a, b = _make_replica_pair(tmp_path)
    with sqlite3.connect(b) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    with pytest.raises(HTTPException, match="rollback-journal"):
        routes_conflicts._write_resolution_atomically(str(a), str(b), "items", 1, "value", "new")
    assert _read(a, "SELECT value FROM items WHERE id=1") == [("old",)]
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("old",)]


def test_null_row_resolution_endpoint_marks_resolved_only_after_both_deletes(tmp_path, monkeypatch):
    from backend.api.state import app_state

    a, b = _make_replica_pair(tmp_path)
    record = {
        "status": "pending", "table": "items", "row_id": 1, "column": "*",
        "value_a": None, "value_b": {"id": 1, "value": "old"},
        "replica_a_id": "a", "replica_b_id": "b",
    }
    stored = []
    monkeypatch.setattr(app_state, "get_conflict", lambda _: record)
    monkeypatch.setattr(app_state, "get_replica_path", lambda rid: str(a if rid == "a" else b))
    monkeypatch.setattr(app_state, "store_conflict", lambda _, value: stored.append(value.copy()))
    monkeypatch.setattr(routes_conflicts._manager, "apply_resolution", lambda *_: None)

    response = routes_conflicts.resolve_conflict(
        ConflictResolveRequest(conflict_id="delete", resolution_mode="pick_a")
    )
    assert response["status"] == "resolved"
    assert _read(a, "SELECT * FROM items") == []
    assert _read(b, "SELECT * FROM items") == []
    assert stored[0]["status"] == "resolved"
    a_tombstone = _read(a, "SELECT origin_id,source_id,source_sequence,depends_on FROM _ss_change_log WHERE op_type='RESOLVE'")
    b_tombstone = _read(b, "SELECT origin_id,source_id,source_sequence,depends_on FROM _ss_change_log WHERE op_type='RESOLVE'")
    assert a_tombstone and b_tombstone and a_tombstone[0] == b_tombstone[0]


def test_null_cell_resolution_updates_both_replicas(tmp_path):
    a, b = _make_replica_pair(tmp_path)
    routes_conflicts._write_resolution_atomically(str(a), str(b), "items", 1, "value", None)
    assert _read(a, "SELECT value FROM items WHERE id=1") == [(None,)]
    assert _read(b, "SELECT value FROM items WHERE id=1") == [(None,)]


def test_missing_row_resolution_fails_without_marking_conflict_resolved(tmp_path, monkeypatch):
    a, b = _make_replica_pair(tmp_path)
    with sqlite3.connect(b) as conn:
        conn.execute("DELETE FROM items WHERE id=1")
        conn.commit()
    record = {
        "status": "pending", "table": "items", "row_id": 1, "column": "value",
        "value_a": "chosen", "value_b": "other", "replica_a_id": "a", "replica_b_id": "b",
    }
    stored = []
    monkeypatch.setattr(routes_conflicts.app_state, "get_conflict", lambda _: record)
    monkeypatch.setattr(routes_conflicts.app_state, "get_replica_path", lambda rid: str(a if rid == "a" else b))
    monkeypatch.setattr(routes_conflicts.app_state, "store_conflict", lambda *_: stored.append(True))
    monkeypatch.setattr(routes_conflicts._manager, "apply_resolution", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        routes_conflicts.resolve_conflict(
            ConflictResolveRequest(conflict_id="missing", resolution_mode="pick_a")
        )
    assert exc.value.status_code == 409
    assert record["status"] == "pending"
    assert stored == []
    assert _read(a, "SELECT value FROM items WHERE id=1") == [("old",)]


def test_second_replica_failure_rolls_back_first_replica_write(tmp_path):
    a, b = _make_replica_pair(tmp_path, trigger_b=True)
    with pytest.raises(HTTPException, match="Atomic conflict write-back failed"):
        routes_conflicts._write_resolution_atomically(str(a), str(b), "items", 1, "value", "new")
    assert _read(a, "SELECT value FROM items WHERE id=1") == [("old",)]
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("old",)]


def test_sync_engine_resolution_failure_rolls_back_both_replicas(tmp_path):
    a, b = _make_replica_pair(tmp_path, trigger_b=True)
    engine = CRDTSyncEngine()
    with pytest.raises(sqlite3.IntegrityError, match="injected update failure"):
        engine._write_resolved_pair(
            str(a), "engine_a", str(b), "engine_b", "items", 1,
            "value", "new", "update",
        )
    assert _read(a, "SELECT value FROM items WHERE id=1") == [("old",)]
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("old",)]


def test_second_replica_failure_keeps_endpoint_conflict_unresolved(tmp_path, monkeypatch):
    from backend.api.state import app_state

    a, b = _make_replica_pair(tmp_path, trigger_b=True)
    record = {
        "status": "pending", "table": "items", "row_id": 1, "column": "value",
        "value_a": "new", "value_b": "other", "replica_a_id": "a", "replica_b_id": "b",
    }
    stored = []
    monkeypatch.setattr(app_state, "get_conflict", lambda _: record)
    monkeypatch.setattr(app_state, "get_replica_path", lambda rid: str(a if rid == "a" else b))
    monkeypatch.setattr(app_state, "store_conflict", lambda *_: stored.append(True))
    monkeypatch.setattr(routes_conflicts._manager, "apply_resolution", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        routes_conflicts.resolve_conflict(
            ConflictResolveRequest(conflict_id="partial", resolution_mode="pick_a")
        )
    assert exc.value.status_code == 500
    assert record["status"] == "pending"
    assert stored == []
    assert _read(a, "SELECT value FROM items WHERE id=1") == [("old",)]
    assert _read(b, "SELECT value FROM items WHERE id=1") == [("old",)]


def test_sync_api_returns_skipped_tables(monkeypatch, tmp_path):
    from backend.api.state import app_state

    a, b = tmp_path / "a.db", tmp_path / "b.db"
    a.touch()
    b.touch()
    monkeypatch.setattr(app_state, "get_db", lambda _: {"path": str(a)})
    monkeypatch.setattr(app_state, "get_replica_path", lambda rid: str(a if rid == "a" else b))
    monkeypatch.setattr(app_state, "get_policies_for_db", lambda _: {})
    monkeypatch.setattr(
        routes_sync._sync_engine,
        "sync_replicas",
        lambda **_: SyncResult(0, 0, 0, [], [], 0.1, skipped_tables=["unsupported"], rejected_operations=[{"operation_id": "held"}]),
    )
    result = routes_sync.run_sync(SyncRequest(db_id="db", replica_a_id="a", replica_b_id="b"))
    assert result["skipped_tables"] == ["unsupported"]
    assert result["rejected_operations"] == [{"operation_id": "held"}]
