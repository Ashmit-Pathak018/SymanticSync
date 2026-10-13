from __future__ import annotations

import sqlite3

import pytest

from backend.api.state import AppState
from backend.engine.crdt_sync import CRDTSyncEngine
from backend.engine.conflict_detector import ConflictDetector
from backend.engine.fk_quarantine import connect_with_foreign_keys
from backend.engine.log_compaction import compact_change_log, compactable_operation_ids, operation_payload_hash


def _db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR IGNORE INTO items VALUES(1, 'base')")


def _op(path):
    with connect_with_foreign_keys(path) as conn:
        return conn.execute(
            "SELECT origin_id,source_id,source_sequence,ts_pt,ts_l FROM _ss_change_log"
        ).fetchone()


def _committed_checkpoint_fixture(tmp_path, monkeypatch, configure_base=None):
    """Create a valid committed checkpoint but inject failure before recovery."""
    import backend.api.routes_sync as routes
    import backend.api.state as state_module
    from backend.engine.checkpoint_store import initialize_checkpoint_store, list_recoverable_checkpoints

    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(state_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(state_module, "REGISTRY_FILE", tmp_path / "registry.json")
    base = tmp_path / "base.db"
    _db(base)
    if configure_base:
        configure_base(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    paths = {replica_id: engine.create_replica(replica_id) for replica_id in ("a", "b")}
    engine.apply_change(paths["a"], "a", "items", 1, "value", "checkpointed")
    engine.sync_replicas(paths["a"], paths["b"], str(base), "a", "b", {})
    store_id = initialize_checkpoint_store(tmp_path / "checkpoint_store.sqlite")
    state = AppState()
    state.databases = {"db": {"path": str(base)}}
    state.replicas = {
        replica_id: {"replica_id": replica_id, "db_path": path, "parent_db_id": "db",
                     "incarnation_id": f"inc-{replica_id}"}
        for replica_id, path in paths.items()
    }
    state.checkpoint_store_id = store_id
    state.replica_acks = {"db": {"a": {}, "b": {}}}
    for replica_id, path in paths.items():
        with connect_with_foreign_keys(path) as conn:
            rows = conn.execute(
                "SELECT origin_id,source_id,source_sequence,ts_pt,ts_l,old_value,new_value,"
                "table_name,row_id,column_name,op_type,depends_on,bounded_delta,bounds_min,bounds_max "
                "FROM _ss_change_log"
            ).fetchall()
        state.record_replica_acknowledgements("db", replica_id, [
            {"operation_id": row[0], "source_id": row[1], "source_sequence": row[2],
             "ts_pt": row[3], "ts_l": row[4],
             "payload_hash": operation_payload_hash(
                 row[5], row[6], row[7], row[8], row[9], row[10], row[1], row[2],
                 row[11], row[12], row[13], row[14],
             )}
            for row in rows
        ])
    state.save()
    monkeypatch.setattr(routes, "app_state", state)
    original_resume = routes._resume_checkpoint

    def stop_before_recovery(_checkpoint):
        raise routes.CheckpointStoreBlocked("injected stop after manifest commit")

    monkeypatch.setattr(routes, "_resume_checkpoint", stop_before_recovery)
    assert routes.compact_sync_logs({"db_id": "db"})["status"] == "blocked"
    monkeypatch.setattr(routes, "_resume_checkpoint", original_resume)
    checkpoint = list_recoverable_checkpoints(tmp_path / "checkpoint_store.sqlite")[0]
    return routes, state, paths, checkpoint


def _rewrite_committed_manifest(tmp_path, checkpoint, manifest):
    import hashlib
    import json

    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with sqlite3.connect(tmp_path / "checkpoint_store.sqlite") as conn:
        conn.execute("UPDATE checkpoints SET manifest_json=?,manifest_hash=? WHERE checkpoint_id=?",
                     (raw, digest, checkpoint["checkpoint_id"]))
    checkpoint["manifest"] = manifest


def _hot_log_state(path):
    with connect_with_foreign_keys(path) as conn:
        return conn.execute(
            "SELECT origin_id,old_value,new_value,table_name,row_id,column_name "
            "FROM _ss_change_log ORDER BY sequence"
        ).fetchall()


def test_ack_registry_persists_and_missing_or_new_replica_pins_horizon(tmp_path, monkeypatch):
    import backend.api.state as state_module

    monkeypatch.setattr(state_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(state_module, "REGISTRY_FILE", tmp_path / "registry.json")
    state = AppState()
    state.register_replica("a", parent_db_id="db", db_path="a.db")
    state.register_replica("b", parent_db_id="db", db_path="b.db")
    state.record_replica_acknowledgements("db", "a", [{
        "operation_id": "op", "source_id": "a", "source_sequence": 1, "ts_pt": 10, "ts_l": 0,
    }])
    assert state.replica_ack_vectors("db", ["a", "b"]) == {}
    state.record_replica_acknowledgements("db", "b", [{
        "operation_id": "op", "source_id": "a", "source_sequence": 1, "ts_pt": 10, "ts_l": 0,
    }])
    restored = AppState()
    restored.load()
    assert restored.replica_ack_vectors("db", ["a", "b"])["b"]["op"]["source_sequence"] == 1
    restored.register_replica("c", parent_db_id="db", db_path="c.db")
    assert restored.replica_ack_vectors("db", ["a", "b"]) == {}
    assert restored.replica_ack_vectors("db", ["a", "b", "c"]) == {}


def test_ack_intersection_and_horizon_require_exact_common_operation_ids():
    vectors = {
        "a": {"one": {"ts_pt": 1, "ts_l": 0, "payload_hash": "h1"}, "two": {"ts_pt": 2, "ts_l": 0, "payload_hash": "h2"}},
        "b": {"one": {"ts_pt": 1, "ts_l": 0, "payload_hash": "h1"}, "three": {"ts_pt": 3, "ts_l": 0, "payload_hash": "h3"}},
    }
    ids, horizon = compactable_operation_ids(vectors)
    assert ids == {"one"}
    assert horizon == (2.0, 0)
    assert compactable_operation_ids({"a": vectors["a"], "offline": {}}) == (set(), None)
    vectors["b"]["one"]["payload_hash"] = "tampered"
    assert compactable_operation_ids(vectors)[0] == set()


def test_compaction_is_strict_transactional_and_restart_safe(tmp_path):
    base = tmp_path / "base.db"
    replica = tmp_path / "replica.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica_path = engine.create_replica("replica")
    engine.apply_change(replica_path, "replica", "items", 1, "value", "changed")
    operation = _op(replica_path)
    op_id = str(operation[0])

    boundary = compact_change_log(replica_path, ["replica", "peer"],
                                  all_acknowledged_ids={op_id},
                                  stable_horizon=(operation[3], operation[4]))
    assert boundary["pruned"] == 0
    result = compact_change_log(replica_path, ["replica", "peer"],
                                all_acknowledged_ids={op_id},
                                stable_horizon=(operation[3] + 1, 0))
    assert result["pruned"] == 1
    with connect_with_foreign_keys(replica_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (op_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts WHERE origin_id=?", (op_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "changed"
        compacted_sequence = conn.execute(
            "SELECT sequence FROM _ss_compacted_receipts WHERE origin_id=?", (op_id,)
        ).fetchone()[0]
    with ConflictDetector._connect(replica_path) as conn:
        archived_ts = ConflictDetector._build_ts_map(conn, "replica")[("items", "1", "value")]
    assert archived_ts == float(operation[3]) * 1e6 + int(operation[4])
    next_id = engine.apply_change(replica_path, "replica", "items", 1, "value", "after-checkpoint")
    with connect_with_foreign_keys(replica_path) as conn:
        next_sequence = conn.execute("SELECT sequence FROM _ss_change_log WHERE origin_id=?", (next_id,)).fetchone()[0]
        assert next_sequence > compacted_sequence
    # SQLite close/reopen models process restart; compacted operation identity survives.
    with connect_with_foreign_keys(replica_path) as conn:
        assert conn.execute("SELECT origin_id FROM _ss_compacted_receipts").fetchone()[0] == op_id


def test_unacknowledged_and_dependency_unclosed_operations_are_retained(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("replica")
    engine.apply_change(replica, "replica", "items", 1, "value", "one")
    first = _op(replica)
    engine.apply_change(replica, "replica", "items", 1, "value", "two")
    with connect_with_foreign_keys(replica) as conn:
        second = conn.execute(
            "SELECT origin_id,source_id,source_sequence,ts_pt,ts_l FROM _ss_change_log ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        conn.execute("UPDATE _ss_change_log SET depends_on=? WHERE origin_id=?", ('["missing-parent"]', second[0]))
        conn.commit()
    result = compact_change_log(replica, ["a", "b"],
                                all_acknowledged_ids={first[0], second[0]},
                                stable_horizon=(max(first[3], second[3]) + 1, 0))
    assert result["pruned"] == 1
    with connect_with_foreign_keys(replica) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (second[0],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (first[0],)).fetchone()[0] == 0


def test_compaction_failure_rolls_back_log_and_receipt_archive(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("replica")
    engine.apply_change(replica, "replica", "items", 1, "value", "changed")
    operation = _op(replica)
    with connect_with_foreign_keys(replica) as conn:
        conn.execute("CREATE TRIGGER block_compact BEFORE DELETE ON _ss_change_log BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="blocked"):
        compact_change_log(replica, ["a", "b"], all_acknowledged_ids={operation[0]},
                           stable_horizon=(operation[3] + 1, 0))
    with connect_with_foreign_keys(replica) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (operation[0],)).fetchone()[0] == 1
        has_archive = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_compacted_receipts'"
        ).fetchone()
        assert not has_archive or conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0


def test_stable_checkpoint_reduces_acknowledged_log_rows_over_seventy_percent(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("replica")
    for value in range(13):
        engine.apply_change(replica, "replica", "items", 1, "value", str(value))
    with connect_with_foreign_keys(replica) as conn:
        rows = conn.execute(
            "SELECT origin_id,ts_pt,ts_l FROM _ss_change_log ORDER BY sequence"
        ).fetchall()
        before = len(rows)
    operation_ids = {str(row[0]) for row in rows}
    horizon = (float(rows[-1][1]), int(rows[-1][2]))
    result = compact_change_log(replica, ["replica", "peer"],
                                all_acknowledged_ids=operation_ids,
                                stable_horizon=horizon)
    with connect_with_foreign_keys(replica) as conn:
        after = conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0]
    assert result["pruned"] == before - after
    assert (before - after) / before > 0.70


def test_payload_mismatch_in_ack_vector_retains_operation(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("replica")
    engine.apply_change(replica, "replica", "items", 1, "value", "actual")
    with connect_with_foreign_keys(replica) as conn:
        row = conn.execute("SELECT origin_id,ts_pt,ts_l FROM _ss_change_log").fetchone()
    result = compact_change_log(
        replica, ["replica", "peer"], all_acknowledged_ids={row[0]},
        stable_horizon=(row[1] + 1, 0), acknowledged_payload_hashes={row[0]: "wrong"},
    )
    assert result["pruned"] == 0
    with connect_with_foreign_keys(replica) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (row[0],)).fetchone()[0] == 1


def test_mutated_receiver_receipt_rolls_back_and_is_not_acknowledged(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    operation_id = engine.apply_change(a, "a", "items", 1, "value", "delivered")
    with connect_with_foreign_keys(b) as conn:
        conn.execute(f"""CREATE TRIGGER mutate_receipt AFTER INSERT ON _ss_change_log
            WHEN NEW.origin_id='{operation_id}' AND NEW.replica_id='b'
            BEGIN UPDATE _ss_change_log SET new_value='corrupt' WHERE id=NEW.id; END""")
        conn.commit()
    result = engine.sync_replicas(a, b, str(base), "a", "b", {})
    assert any(item["operation_id"] == operation_id for item in result.rejected_operations)
    assert not any(item["replica_id"] == "b" and item["operation_id"] == operation_id
                   for item in result.acknowledgements)
    with connect_with_foreign_keys(b) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "base"
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?",
                            (operation_id,)).fetchone()[0] == 0


def test_duplicate_replay_after_compaction_uses_receipt_ledger(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    engine.apply_change(a, "a", "items", 1, "value", "updated")
    engine.sync_replicas(a, b, str(base), "a", "b", {})
    operation = _op(a)
    # Simulate exact ACK evidence from every enrolled replica on both files.
    ack = {operation[0]}
    horizon = (operation[3] + 1, 0)
    assert compact_change_log(b, ["a", "b"], all_acknowledged_ids=ack, stable_horizon=horizon)["pruned"] == 1
    engine.sync_replicas(a, b, str(base), "a", "b", {})
    with connect_with_foreign_keys(b) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "updated"
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts WHERE origin_id=?", (operation[0],)).fetchone()[0] == 1


def test_three_replica_ack_order_and_delayed_replica_pin_compaction(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    paths = {name: engine.create_replica(name) for name in ("a", "b", "c")}
    operation_id = engine.apply_change(paths["a"], "a", "items", 1, "value", "mesh")
    # Relay via B, then in reversed edge order. C does not acknowledge until the second edge.
    engine.sync_replicas(paths["a"], paths["b"], str(base), "a", "b", {})
    arow = _op(paths["a"])
    with connect_with_foreign_keys(paths["c"]) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "base"
    partial = {"a": {operation_id: {"ts_pt": arow[3], "ts_l": arow[4], "payload_hash": "h"}},
               "b": {operation_id: {"ts_pt": arow[3], "ts_l": arow[4], "payload_hash": "h"}}, "c": {}}
    assert compactable_operation_ids(partial) == (set(), None)
    engine.sync_replicas(paths["c"], paths["b"], str(base), "c", "b", {})
    with connect_with_foreign_keys(paths["c"]) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "mesh"
    complete = {rid: {operation_id: {"ts_pt": arow[3], "ts_l": arow[4], "payload_hash": "h"}} for rid in paths}
    common, horizon = compactable_operation_ids(complete)
    assert common == {operation_id} and horizon is not None
    for path in paths.values():
        assert compact_change_log(path, list(paths), all_acknowledged_ids=common,
                                  stable_horizon=(arow[3] + 1, 0))["pruned"] == 1
    # Restart and duplicate/reordered pair syncs remain safe after compaction.
    restarted = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    restarted.sync_replicas(paths["c"], paths["a"], str(base), "c", "a", {})
    restarted.sync_replicas(paths["a"], paths["c"], str(base), "a", "c", {})
    for path in paths.values():
        with connect_with_foreign_keys(path) as conn:
            assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "mesh"
            assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts WHERE origin_id=?",
                                (operation_id,)).fetchone()[0] == 1


def test_compacted_log_checkpoint_bootstraps_new_replica_from_materialized_peer(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    a = engine.create_replica("a")
    b = engine.create_replica("b")
    operation_id = engine.apply_change(a, "a", "items", 1, "value", "checkpoint")
    engine.sync_replicas(a, b, str(base), "a", "b", {})
    row = _op(a)
    for path in (a, b):
        assert compact_change_log(path, ["a", "b"], all_acknowledged_ids={operation_id},
                                  stable_horizon=(row[3] + 1, 0))["pruned"] == 1
    c = engine.create_replica("c", snapshot_path=b)
    with connect_with_foreign_keys(c) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "checkpoint"
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts WHERE origin_id=?",
                            (operation_id,)).fetchone()[0] == 1


def test_delete_reinsert_chain_compacts_without_resurrecting_stale_tombstone(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    paths = {name: engine.create_replica(name) for name in ("a", "b", "c")}
    delete_id = engine.apply_delete(paths["a"], "a", "items", 1)
    engine.sync_replicas(paths["a"], paths["b"], str(base), "a", "b", {})
    engine.sync_replicas(paths["c"], paths["b"], str(base), "c", "b", {})
    insert_id = engine.apply_insert(paths["a"], "a", "items", {"id": 1, "value": "reinserted"})
    sentinel_id = engine.apply_change(paths["a"], "a", "items", 1, "value", "latest")
    engine.sync_replicas(paths["a"], paths["b"], str(base), "a", "b", {})
    engine.sync_replicas(paths["b"], paths["c"], str(base), "b", "c", {})
    with connect_with_foreign_keys(paths["a"]) as conn:
        horizon_row = conn.execute(
            "SELECT ts_pt,ts_l FROM _ss_change_log WHERE origin_id=?", (sentinel_id,)
        ).fetchone()
    ids = {delete_id, insert_id, sentinel_id}
    for path in paths.values():
        result = compact_change_log(
            path, list(paths), all_acknowledged_ids=ids,
            stable_horizon=(horizon_row[0], horizon_row[1]),
        )
        assert result["pruned"] == 2
    restarted = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    restarted.sync_replicas(paths["c"], paths["a"], str(base), "c", "a", {})
    for path in paths.values():
        with connect_with_foreign_keys(path) as conn:
            assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "latest"
            archived = dict(conn.execute(
                "SELECT op_type,COUNT(*) FROM _ss_compacted_receipts "
                "WHERE origin_id IN (?,?) GROUP BY op_type", (delete_id, insert_id)
            ).fetchall())
            assert archived == {"DELETE": 1, "INSERT": 1}


def test_checkpoint_store_is_explicit_durable_and_fails_closed_on_loss_or_corruption(tmp_path):
    from backend.engine.checkpoint_store import (
        CheckpointStoreBlocked, initialize_checkpoint_store, validate_checkpoint_store,
    )

    missing = tmp_path / "missing.sqlite"
    with pytest.raises(CheckpointStoreBlocked, match="missing"):
        validate_checkpoint_store(missing)
    assert not missing.exists(), "validation must never create an empty authority store"

    store = tmp_path / "checkpoint.sqlite"
    store_id = initialize_checkpoint_store(store)
    staging = store.with_name(store.name + ".initializing")
    store.replace(staging)  # crash after durable initialization, before atomic publication
    assert initialize_checkpoint_store(store) == store_id
    assert validate_checkpoint_store(store, expected_store_id=store_id)["status"] == "ready"
    with sqlite3.connect(store) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    from backend.engine.checkpoint_store import _connect
    conn = _connect(store)
    try:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    finally:
        conn.close()
    original = store.read_bytes()
    store.write_bytes(b"not a sqlite database")
    with pytest.raises(CheckpointStoreBlocked):
        validate_checkpoint_store(store, expected_store_id=store_id)
    assert store.read_bytes() == b"not a sqlite database", "corrupt store must be preserved for inspection"
    assert original


def test_checkpoint_archive_and_journal_retries_are_idempotent(tmp_path):
    from backend.engine.checkpoint_store import (
        CheckpointStoreBlocked, initialize_checkpoint_store, set_checkpoint_state,
        validate_checkpoint_store, write_checkpoint_record,
    )

    store = tmp_path / "checkpoint.sqlite"
    store_id = initialize_checkpoint_store(store)
    checkpoint_id = "cp-stable"
    operation = {"operation_id": "op-1", "payload_hash": "payload-digest"}
    manifest = {"checkpoint_id": checkpoint_id, "store_id": store_id, "replicas": [], "snapshots": [],
                "operation_hashes": {"op-1": "payload-digest"}}
    write_checkpoint_record(store, checkpoint_id, manifest, [operation])
    write_checkpoint_record(store, checkpoint_id, manifest, [operation])
    set_checkpoint_state(store, checkpoint_id, "PRUNING")
    set_checkpoint_state(store, checkpoint_id, "PRUNING")
    set_checkpoint_state(store, checkpoint_id, "COMPLETE")
    set_checkpoint_state(store, checkpoint_id, "COMPLETE")
    assert validate_checkpoint_store(store)["checkpoints"] == 1
    with sqlite3.connect(store) as conn:
        assert conn.execute("SELECT COUNT(*) FROM archived_operations WHERE operation_id='op-1'").fetchone()[0] == 1
        assert conn.execute("SELECT state FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone()[0] == "COMPLETE"
    with pytest.raises(CheckpointStoreBlocked, match="different manifest"):
        write_checkpoint_record(store, checkpoint_id, {**manifest, "db_id": "tampered"}, [operation])
    with sqlite3.connect(store) as conn:
        conn.execute("UPDATE checkpoints SET manifest_json='{}' WHERE checkpoint_id=?", (checkpoint_id,))
    with pytest.raises(CheckpointStoreBlocked, match="manifest hash mismatch"):
        validate_checkpoint_store(store)


def test_compaction_api_recovers_committed_checkpoint_idempotently_after_restart(tmp_path, monkeypatch):
    import backend.api.routes_sync as routes
    import backend.api.state as state_module
    from backend.engine.checkpoint_store import initialize_checkpoint_store, list_recoverable_checkpoints

    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(state_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(state_module, "REGISTRY_FILE", tmp_path / "registry.json")
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    a, b = engine.create_replica("a"), engine.create_replica("b")
    engine.apply_change(a, "a", "items", 1, "value", "first")
    engine.apply_change(a, "a", "items", 1, "value", "second")
    engine.sync_replicas(a, b, str(base), "a", "b", {})

    store_id = initialize_checkpoint_store(tmp_path / "checkpoint_store.sqlite")
    state = AppState()
    state.databases = {"db": {"path": str(base)}}
    state.replicas = {
        "a": {"replica_id": "a", "db_path": a, "parent_db_id": "db", "incarnation_id": "inc-a"},
        "b": {"replica_id": "b", "db_path": b, "parent_db_id": "db", "incarnation_id": "inc-b"},
    }
    state.checkpoint_store_id = store_id
    state.replica_acks = {"db": {"a": {}, "b": {}}}
    for replica_id, path in (("a", a), ("b", b)):
        with connect_with_foreign_keys(path) as conn:
            rows = conn.execute("SELECT origin_id,source_id,source_sequence,ts_pt,ts_l,old_value,new_value,table_name,row_id,column_name,op_type,depends_on,bounded_delta,bounds_min,bounds_max FROM _ss_change_log").fetchall()
        state.record_replica_acknowledgements("db", replica_id, [
            {"operation_id": row[0], "source_id": row[1], "source_sequence": row[2],
             "ts_pt": row[3], "ts_l": row[4],
             "payload_hash": operation_payload_hash(row[5], row[6], row[7], row[8], row[9], row[10], row[1], row[2], row[11], row[12], row[13], row[14])}
            for row in rows
        ])
    monkeypatch.setattr(routes, "app_state", state)
    original_resume = routes._resume_checkpoint

    def crash_after_manifest(checkpoint):
        raise routes.CheckpointStoreBlocked("injected crash after committed manifest")

    monkeypatch.setattr(routes, "_resume_checkpoint", crash_after_manifest)
    result = routes.compact_sync_logs({"db_id": "db"})
    assert result["status"] == "blocked"
    with connect_with_foreign_keys(a) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == 2

    # Simulate process restart by loading the durable registry into a new state.
    state.replica_acks = {"db": {"a": {}, "b": {}}}
    state.save()
    restarted = AppState()
    restarted.load()
    monkeypatch.setattr(routes, "app_state", restarted)
    checkpoint = list_recoverable_checkpoints(tmp_path / "checkpoint_store.sqlite")[0]
    snapshot_path = __import__("pathlib").Path(checkpoint["manifest"]["snapshots"][0]["path"])
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot_path.write_bytes(b"corrupt snapshot")
    assert routes._checkpoint_store_status()["status"] == "blocked"
    with connect_with_foreign_keys(a) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0
    snapshot_path.write_bytes(snapshot_bytes)
    with connect_with_foreign_keys(b) as conn:
        original_value = conn.execute("SELECT new_value FROM _ss_change_log ORDER BY sequence LIMIT 1").fetchone()[0]
        conn.execute("UPDATE _ss_change_log SET new_value='tampered' WHERE sequence=(SELECT MIN(sequence) FROM _ss_change_log)")
        conn.commit()
    with pytest.raises(routes.CheckpointStoreBlocked, match="hash mismatch|no longer matches|history changed"):
        original_resume(checkpoint)
    with connect_with_foreign_keys(a) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0
    with connect_with_foreign_keys(b) as conn:
        conn.execute("UPDATE _ss_change_log SET new_value=? WHERE sequence=(SELECT MIN(sequence) FROM _ss_change_log)", (original_value,))
        conn.commit()
    original_compact = routes.compact_change_log
    compacted = set()

    def crash_after_first_replica(*args, **kwargs):
        path = args[0]
        if not compacted:
            result = original_compact(*args, **kwargs)
            compacted.add(path)
            return result
        raise routes.CheckpointStoreBlocked("injected crash between replica prune transactions")

    monkeypatch.setattr(routes, "_resume_checkpoint", original_resume)
    monkeypatch.setattr(routes, "compact_change_log", crash_after_first_replica)
    partial = routes.compact_sync_logs({"db_id": "db"})
    assert partial["status"] == "blocked"
    with connect_with_foreign_keys(a) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 1
    with connect_with_foreign_keys(b) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0

    monkeypatch.setattr(routes, "compact_change_log", original_compact)
    # Simulate restart with one replica pruned and the other untouched.
    restarted = AppState()
    restarted.load()
    monkeypatch.setattr(routes, "app_state", restarted)
    first = original_resume(checkpoint)
    assert set(restarted.replica_acks["db"]["a"]) == set(checkpoint["manifest"]["acknowledgements"]["a"])
    second = original_resume(checkpoint)
    assert first["pruned"] == 1
    assert second["pruned"] == 0 and second["replayed"] is True
    for path in (a, b):
        with connect_with_foreign_keys(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == 1


def test_recovery_preserves_tracked_update_written_after_manifest_commit(tmp_path, monkeypatch):
    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    engine = CRDTSyncEngine()
    tail_id = engine.apply_change(paths["a"], "a", "items", 1, "value", "after-commit")
    before_tail = _hot_log_state(paths["a"])

    # Restart after the manifest commit and tracked tail write, before recovery.
    restarted = AppState()
    restarted.load()
    monkeypatch.setattr(routes, "app_state", restarted)

    first = routes._resume_checkpoint(checkpoint)
    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "after-commit"
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (tail_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts WHERE origin_id=?", (tail_id,)).fetchone()[0] == 0
    assert first["checkpoint_id"] == checkpoint["checkpoint_id"]

    # A second recovery call models retry after recovery itself.
    replay = routes._resume_checkpoint(checkpoint)
    assert replay["replayed"] is True
    assert "inc-a" == restarted.get_replica("a")["incarnation_id"]
    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "after-commit"
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (tail_id,)).fetchone()[0] == 1
    assert any(row[0] == tail_id for row in before_tail)


@pytest.mark.parametrize("mutation", ["insert", "delete"])
def test_recovery_validates_tracked_insert_and_delete_tails(tmp_path, monkeypatch, mutation):
    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    engine = CRDTSyncEngine()
    if mutation == "insert":
        operation_id = engine.apply_insert(paths["a"], "a", "items", {"id": 2, "value": "new-row"})
    else:
        operation_id = engine.apply_delete(paths["a"], "a", "items", 1)
    with connect_with_foreign_keys(paths["a"]) as conn:
        expected_rows = conn.execute("SELECT id,value FROM items ORDER BY id").fetchall()

    restarted = AppState()
    restarted.load()
    monkeypatch.setattr(routes, "app_state", restarted)
    result = routes._resume_checkpoint(checkpoint)
    assert result["checkpoint_id"] == checkpoint["checkpoint_id"]
    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute("SELECT id,value FROM items ORDER BY id").fetchall() == expected_rows
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (operation_id,)).fetchone()[0] == 1


def test_inconsistent_post_manifest_tail_blocks_without_ack_or_log_changes(tmp_path, monkeypatch):
    from copy import deepcopy
    from backend.engine.checkpoint_store import checkpoint_state

    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    operation_id = CRDTSyncEngine().apply_change(
        paths["a"], "a", "items", 1, "value", "tracked-tail",
    )
    # Model an untracked edit after the tracked operation: the log claims one
    # result while the materialized row contains another.
    with sqlite3.connect(paths["a"]) as conn:
        conn.execute("UPDATE items SET value='untracked-drift' WHERE id=1")
    logs_before = {replica_id: _hot_log_state(path) for replica_id, path in paths.items()}
    acks_before = deepcopy(state.replica_acks)
    with connect_with_foreign_keys(paths["a"]) as conn:
        receipts_before = conn.execute(
            "SELECT origin_id,payload_hash FROM _ss_compacted_receipts ORDER BY origin_id"
        ).fetchall()

    with pytest.raises(routes.CheckpointStoreBlocked, match="data does not match tracked operation tail"):
        routes._resume_checkpoint(checkpoint)

    assert state.replica_acks == acks_before
    assert {replica_id: _hot_log_state(path) for replica_id, path in paths.items()} == logs_before
    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute(
            "SELECT origin_id,payload_hash FROM _ss_compacted_receipts ORDER BY origin_id"
        ).fetchall() == receipts_before
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "untracked-drift"
    assert checkpoint_state(tmp_path / "checkpoint_store.sqlite", checkpoint["checkpoint_id"]) == "COMMITTED"


@pytest.mark.parametrize("malformation", ["dependency", "sequence", "duplicate_id", "trigger_effect"])
def test_malformed_post_manifest_tails_block_without_state_changes(
    tmp_path, monkeypatch, malformation,
):
    """Each malformed tail must fail before ACK reconciliation or pruning."""
    from copy import deepcopy
    import json
    from backend.engine.checkpoint_store import checkpoint_state

    def configure_trigger(base):
        with sqlite3.connect(base) as conn:
            conn.execute("ALTER TABLE items ADD COLUMN marker TEXT DEFAULT 'initial'")
            conn.execute("""
                CREATE TRIGGER mutate_tail_marker AFTER UPDATE OF value ON items
                WHEN NEW.value='tail-trigger'
                BEGIN
                    UPDATE items SET marker=hex(randomblob(8)) WHERE id=NEW.id;
                END
            """)
            conn.commit()

    routes, state, paths, checkpoint = _committed_checkpoint_fixture(
        tmp_path, monkeypatch,
        configure_base=configure_trigger if malformation == "trigger_effect" else None,
    )
    engine = CRDTSyncEngine()
    target_value = "tail-trigger" if malformation == "trigger_effect" else "tail-value"
    operation_id = engine.apply_change(paths["a"], "a", "items", 1, "value", target_value)

    with connect_with_foreign_keys(paths["a"]) as conn:
        if malformation == "dependency":
            conn.execute("UPDATE _ss_change_log SET depends_on=? WHERE origin_id=?",
                         (json.dumps(["missing-operation"]), operation_id))
        elif malformation == "sequence":
            # Zero is below the captured snapshot frontier and remains unique.
            conn.execute("UPDATE _ss_change_log SET sequence=0 WHERE origin_id=?",
                         (operation_id,))
        elif malformation == "duplicate_id":
            row = conn.execute(
                "SELECT id,table_name,row_id,column_name,old_value,new_value,ts_pt,ts_l,replica_id,"
                "applied_at,op_type,origin_id,sequence,source_id,source_sequence,depends_on,"
                "bounded_delta,bounds_min,bounds_max FROM _ss_change_log WHERE origin_id=?",
                (operation_id,),
            ).fetchone()
            duplicate = ("duplicate-log-row", *row[1:12], row[12] + 1, *row[13:])
            conn.execute(
                "INSERT INTO _ss_change_log (id,table_name,row_id,column_name,old_value,new_value,"
                "ts_pt,ts_l,replica_id,applied_at,op_type,origin_id,sequence,source_id,"
                "source_sequence,depends_on,bounded_delta,bounds_min,bounds_max) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", duplicate,
            )
        conn.commit()

    # Capture the deliberately malformed but still live state. Recovery must
    # leave it exactly as found, and must not append receipts or repair ACKs.
    with connect_with_foreign_keys(paths["a"]) as conn:
        data_before = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
        log_before = conn.execute(
            "SELECT * FROM _ss_change_log ORDER BY sequence,id"
        ).fetchall()
        receipt_before = conn.execute(
            "SELECT * FROM _ss_compacted_receipts ORDER BY origin_id"
        ).fetchall()
    acks_before = deepcopy(state.replica_acks)
    checkpoint_before = checkpoint_state(tmp_path / "checkpoint_store.sqlite", checkpoint["checkpoint_id"])

    with pytest.raises(routes.CheckpointStoreBlocked):
        routes._resume_checkpoint(checkpoint)

    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute("SELECT * FROM items ORDER BY id").fetchall() == data_before
        assert conn.execute("SELECT * FROM _ss_change_log ORDER BY sequence,id").fetchall() == log_before
        assert conn.execute(
            "SELECT * FROM _ss_compacted_receipts ORDER BY origin_id"
        ).fetchall() == receipt_before
    assert state.replica_acks == acks_before
    assert checkpoint_state(tmp_path / "checkpoint_store.sqlite", checkpoint["checkpoint_id"]) == checkpoint_before == "COMMITTED"


def test_ack_conflict_preflight_changes_no_replica_vector_or_hot_log(tmp_path, monkeypatch):
    from copy import deepcopy

    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    db_acks = state.replica_acks["db"]
    expected = checkpoint["manifest"]["acknowledgements"]
    db_acks["a"] = {}  # Earlier member has a repairable gap.
    operation_id = next(iter(expected["b"]))
    db_acks["b"][operation_id] = {**expected["b"][operation_id], "payload_hash": "conflicting"}
    state.save()
    ack_before = deepcopy(state.replica_acks)
    logs_before = {replica_id: _hot_log_state(path) for replica_id, path in paths.items()}

    with pytest.raises(routes.CheckpointStoreBlocked, match="conflicts"):
        routes._resume_checkpoint(checkpoint)

    assert state.replica_acks == ack_before
    assert {replica_id: _hot_log_state(path) for replica_id, path in paths.items()} == logs_before


def test_ack_reconciliation_partial_failure_restarts_and_retries_idempotently(tmp_path, monkeypatch):
    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    state.replica_acks["db"] = {"a": {}, "b": {}}
    state.save()
    original_save = state.save

    def fail_after_second_vector_mutates():
        if state.replica_acks.get("db", {}).get("b"):
            raise OSError("injected registry publication failure after in-memory ACK mutation")
        return original_save()

    state.save = fail_after_second_vector_mutates
    logs_before = {replica_id: _hot_log_state(path) for replica_id, path in paths.items()}
    with pytest.raises(routes.CheckpointStoreBlocked, match="ACK reconciliation failed"):
        routes._resume_checkpoint(checkpoint)
    assert state.replica_acks["db"]["a"] == checkpoint["manifest"]["acknowledgements"]["a"]
    assert state.replica_acks["db"]["b"] == {}
    assert state.durable_replica_ack_vector("db", "b") == {}
    assert {replica_id: _hot_log_state(path) for replica_id, path in paths.items()} == logs_before

    # Retry in the same process after restoring registry writes, then verify
    # the published ACK and completed checkpoint survive a fresh state load.
    state.save = original_save
    first = routes._resume_checkpoint(checkpoint)
    assert first["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert state.durable_replica_ack_vector("db", "b") == checkpoint["manifest"]["acknowledgements"]["b"]
    restarted = AppState()
    restarted.load()
    monkeypatch.setattr(routes, "app_state", restarted)
    second = routes._resume_checkpoint(checkpoint)
    assert second["replayed"] is True
    assert restarted.replica_acks["db"] == checkpoint["manifest"]["acknowledgements"]
    for path in paths.values():
        with connect_with_foreign_keys(path) as conn:
            hot = {row[0] for row in conn.execute("SELECT COALESCE(origin_id,id) FROM _ss_change_log")}
            receipts = {row[0] for row in conn.execute("SELECT origin_id FROM _ss_compacted_receipts")}
            assert hot | receipts == set(checkpoint["manifest"]["operation_hashes"])
            assert not (hot & receipts)


def test_blocked_resolve_checkpoint_does_not_block_unrelated_compaction_or_sync(tmp_path, monkeypatch):
    import backend.api.routes_sync as routes
    from backend.api.models import SyncRequest
    from backend.engine.checkpoint_store import checkpoint_state

    routes, state, paths, blocked_checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    tail_id = CRDTSyncEngine().apply_change(paths["a"], "a", "items", 1, "value", "tail")
    with connect_with_foreign_keys(paths["a"]) as conn:
        conn.execute("UPDATE _ss_change_log SET op_type='RESOLVE' WHERE origin_id=?", (tail_id,))
        conn.commit()

    second_base = tmp_path / "second_base.db"
    _db(second_base)
    second_engine = CRDTSyncEngine(str(second_base), data_dir=str(tmp_path))
    c, d = second_engine.create_replica("c"), second_engine.create_replica("d")
    second_engine.apply_change(c, "c", "items", 1, "value", "second-database")
    second_engine.sync_replicas(c, d, str(second_base), "c", "d", {})
    state.databases["db2"] = {"id": "db2", "path": str(second_base)}
    state.replicas.update({
        replica_id: {"replica_id": replica_id, "db_path": path, "parent_db_id": "db2",
                     "incarnation_id": f"inc-{replica_id}"}
        for replica_id, path in (("c", c), ("d", d))
    })
    state.replica_acks["db2"] = {"c": {}, "d": {}}
    for replica_id, path in (("c", c), ("d", d)):
        with connect_with_foreign_keys(path) as conn:
            rows = conn.execute(
                "SELECT origin_id,source_id,source_sequence,ts_pt,ts_l,old_value,new_value,"
                "table_name,row_id,column_name,op_type,depends_on,bounded_delta,bounds_min,bounds_max "
                "FROM _ss_change_log"
            ).fetchall()
        state.record_replica_acknowledgements("db2", replica_id, [
            {"operation_id": row[0], "source_id": row[1], "source_sequence": row[2],
             "ts_pt": row[3], "ts_l": row[4],
             "payload_hash": operation_payload_hash(
                 row[5], row[6], row[7], row[8], row[9], row[10], row[1], row[2],
                 row[11], row[12], row[13], row[14],
             )}
            for row in rows
        ])

    compact_result = routes.compact_sync_logs({"db_id": "db2"})
    assert compact_result["status"] == "completed"
    assert compact_result["blocked_checkpoints"] == [{
        "checkpoint_id": blocked_checkpoint["checkpoint_id"],
        "db_id": "db",
        "reason": "post-checkpoint RESOLVE cannot be safely replay-validated: a",
    }]
    assert checkpoint_state(tmp_path / "checkpoint_store.sqlite", blocked_checkpoint["checkpoint_id"]) == "COMMITTED"
    with connect_with_foreign_keys(paths["a"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id=?", (tail_id,)).fetchone()[0] == 1

    sync_result = routes.run_sync(SyncRequest(db_id="db2", replica_a_id="c", replica_b_id="d"))
    assert sync_result["status"] == "completed"
    assert sync_result["blocked_checkpoints"] == compact_result["blocked_checkpoints"]


def test_direct_compaction_call_waits_for_shared_mutation_lock(tmp_path):
    import threading
    from backend.engine.mutation_lock import MUTATION_CHECKPOINT_LOCK

    base = tmp_path / "base.db"
    _db(base)
    replica = CRDTSyncEngine(str(base), data_dir=str(tmp_path)).create_replica("lock-test")
    finished = threading.Event()

    def direct_call():
        compact_change_log(replica, ["lock-test"], all_acknowledged_ids=set(), stable_horizon=None)
        finished.set()

    with MUTATION_CHECKPOINT_LOCK:
        worker = threading.Thread(target=direct_call)
        worker.start()
        assert not finished.wait(0.05)
    worker.join(timeout=2)
    assert finished.is_set()


def test_quarantine_resolution_route_is_shared_lock_wrapped():
    from backend.api.routes_quarantine import resolve_quarantine

    # functools.wraps preserves the route function only when serialized_mutation
    # is applied, making this a direct regression against accidental decorator removal.
    assert hasattr(resolve_quarantine, "__wrapped__")


def test_compaction_api_blocks_without_recreating_missing_or_corrupt_store(tmp_path, monkeypatch):
    import backend.api.routes_sync as routes
    from backend.engine.checkpoint_store import initialize_checkpoint_store

    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    base = tmp_path / "base.db"
    _db(base)
    replica = CRDTSyncEngine(str(base), data_dir=str(tmp_path)).create_replica("a")
    state = AppState()
    state.databases = {"db": {"path": str(base)}}
    state.replicas = {"a": {"replica_id": "a", "db_path": replica, "parent_db_id": "db"}}
    state.checkpoint_store_id = "expected-id"
    monkeypatch.setattr(routes, "app_state", state)
    result = routes.compact_sync_logs({"db_id": "db"})
    assert result["status"] == "blocked"
    assert not (tmp_path / "checkpoint_store.sqlite").exists()
    with connect_with_foreign_keys(replica) as conn:
        before = conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0]
    store = tmp_path / "checkpoint_store.sqlite"
    initialize_checkpoint_store(store)
    store.write_bytes(b"damaged")
    result = routes.compact_sync_logs({"db_id": "db"})
    assert result["status"] == "blocked"
    assert store.read_bytes() == b"damaged"
    with connect_with_foreign_keys(replica) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == before


def test_missing_store_with_compacted_replica_evidence_cannot_be_reinitialized(tmp_path, monkeypatch):
    import backend.api.routes_sync as routes

    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("prior")
    operation_id = engine.apply_change(replica, "prior", "items", 1, "value", "compacted")
    with connect_with_foreign_keys(replica) as conn:
        row = conn.execute("SELECT ts_pt,ts_l FROM _ss_change_log WHERE origin_id=?", (operation_id,)).fetchone()
    compact_change_log(replica, ["prior", "peer"], all_acknowledged_ids={operation_id},
                       stable_horizon=(row[0] + 1, row[1]))
    state = AppState()
    state.replicas = {"prior": {"replica_id": "prior", "db_path": replica, "parent_db_id": "db"}}
    monkeypatch.setattr(routes, "app_state", state)
    assert routes._checkpoint_store_status()["status"] == "blocked"
    result = routes.initialize_sync_checkpoint_store()
    assert result["status"] == "blocked"
    assert not (tmp_path / "checkpoint_store.sqlite").exists()


def test_corrupt_registry_blocks_checkpoint_status_without_overwrite(tmp_path, monkeypatch):
    import backend.api.routes_sync as routes

    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    state = AppState()
    state.registry_load_error = "registry JSON is corrupt"
    monkeypatch.setattr(routes, "app_state", state)
    assert routes._checkpoint_store_status() == {"status": "blocked", "reason": "registry JSON is corrupt"}
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        state.save()
    assert not (tmp_path / "checkpoint_store.sqlite").exists()


def test_snapshot_and_tracked_mutation_share_checkpoint_lock(tmp_path):
    import threading
    import time

    from backend.engine.checkpoint_store import create_database_snapshot
    from backend.engine.mutation_lock import MUTATION_CHECKPOINT_LOCK

    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    replica = engine.create_replica("locked")
    started = threading.Event()
    finished = threading.Event()

    def write():
        started.set()
        engine.apply_change(replica, "locked", "items", 1, "value", "after-lock")
        finished.set()

    with MUTATION_CHECKPOINT_LOCK:
        worker = threading.Thread(target=write)
        worker.start()
        assert started.wait(1)
        time.sleep(0.05)
        assert not finished.is_set()
        snapshot_hash = create_database_snapshot(base, tmp_path / "locked-snapshot.sqlite")
        assert snapshot_hash
    worker.join(timeout=2)
    assert finished.is_set()


def test_replica_reseed_never_overwrites_existing_offline_database(tmp_path):
    base = tmp_path / "base.db"
    _db(base)
    engine = CRDTSyncEngine(str(base), data_dir=str(tmp_path))
    offline = engine.create_replica("offline")
    engine.apply_change(offline, "offline", "items", 1, "value", "local-only")
    before = __import__("pathlib").Path(offline).read_bytes()
    with pytest.raises(FileExistsError, match="will not be overwritten"):
        engine.create_replica("offline", snapshot_path=str(base))
    assert __import__("pathlib").Path(offline).read_bytes() == before
    with connect_with_foreign_keys(offline) as conn:
        assert conn.execute("SELECT value FROM items WHERE id=1").fetchone()[0] == "local-only"


def test_preparing_checkpoint_is_never_recovered_as_committed(tmp_path):
    import hashlib
    import json

    from backend.engine.checkpoint_store import initialize_checkpoint_store, list_recoverable_checkpoints

    store = tmp_path / "checkpoint.sqlite"
    initialize_checkpoint_store(store)
    manifest = {"checkpoint_id": "incomplete", "snapshots": [], "operation_hashes": {}}
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with sqlite3.connect(store) as conn:
        conn.execute("INSERT INTO checkpoints VALUES(?,?,?,?,datetime('now'))",
                     ("incomplete", "PREPARING", raw, digest))
    assert list_recoverable_checkpoints(store) == []


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "swapped", "wrong-replica", "wrong-schema", "frontier"])
def test_committed_checkpoint_snapshot_binding_fails_before_ack_or_prune(tmp_path, monkeypatch, tamper):
    from copy import deepcopy

    from backend.engine.checkpoint_store import list_recoverable_checkpoints

    routes, state, paths, checkpoint = _committed_checkpoint_fixture(tmp_path, monkeypatch)
    manifest = deepcopy(checkpoint["manifest"])
    snapshots = manifest["snapshots"]
    if tamper == "missing":
        manifest["snapshots"].pop()
    elif tamper == "duplicate":
        manifest["snapshots"].append(deepcopy(snapshots[0]))
    elif tamper == "swapped":
        snapshots[0]["path"], snapshots[1]["path"] = snapshots[1]["path"], snapshots[0]["path"]
        snapshots[0]["sha256"], snapshots[1]["sha256"] = snapshots[1]["sha256"], snapshots[0]["sha256"]
    elif tamper == "wrong-replica":
        snapshots[0]["replica_id"] = "unexpected"
    elif tamper == "wrong-schema":
        snapshots[0]["schema_fingerprint"] = "0" * 64
    else:
        operation_id = next(iter(manifest["operation_hashes"]))
        snapshots[0]["operation_frontier"][operation_id] = "f" * 64
    _rewrite_committed_manifest(tmp_path, checkpoint, manifest)
    persisted = list_recoverable_checkpoints(tmp_path / "checkpoint_store.sqlite")[0]
    before_logs = {replica_id: _hot_log_state(path) for replica_id, path in paths.items()}
    before_acks = deepcopy(state.replica_acks)

    with pytest.raises(routes.CheckpointStoreBlocked):
        routes._resume_checkpoint(persisted)

    assert state.replica_acks == before_acks, "invalid snapshot must be rejected before ACK reconciliation"
    for replica_id, path in paths.items():
        assert _hot_log_state(path) == before_logs[replica_id], "invalid snapshot must not prune hot logs"
        with connect_with_foreign_keys(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM _ss_compacted_receipts").fetchone()[0] == 0