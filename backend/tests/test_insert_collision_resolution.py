"""Manual resolution safety for PK and secondary-UNIQUE INSERT conflicts."""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi import HTTPException

from backend.api import routes_conflicts
from backend.api.models import ConflictResolveRequest
from backend.api.state import AppState


PAYLOAD_A = {"id": 1, "code": "shared", "value": "A"}
PAYLOAD_B_PK = {"id": 1, "code": "shared", "value": "B"}
PAYLOAD_B_UNIQUE = {"id": 2, "code": "shared", "value": "B"}


def _db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, value TEXT NOT NULL)")
        conn.executemany("INSERT INTO items VALUES (?, ?, ?)", rows)
        conn.commit()


def _rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT id, code, value FROM items ORDER BY id").fetchall()


def _resolution_logs(path):
    with sqlite3.connect(path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_ss_change_log'"
        ).fetchone()
        if not exists:
            return []
        return conn.execute(
            "SELECT origin_id, source_id, source_sequence, old_value, new_value "
            "FROM _ss_change_log WHERE op_type='RESOLVE'"
        ).fetchall()


@pytest.fixture
def resolution_case(tmp_path, monkeypatch):
    import backend.api.state as state_module

    a, b = tmp_path / "a.db", tmp_path / "b.db"
    _db(a, [(1, "shared", "A")])
    _db(b, [(1, "shared", "B")])
    state_module.DATA_DIR = tmp_path
    state_module.REGISTRY_FILE = tmp_path / "registry.json"
    state = AppState()
    monkeypatch.setattr(routes_conflicts, "app_state", state)
    monkeypatch.setattr(routes_conflicts._manager, "apply_resolution", lambda *_: None)
    record = {
        "conflict_id": "pk-conflict", "db_id": "db", "table": "items", "row_id": 1,
        "column": "*", "conflict_type": "INSERT_INSERT", "status": "flagged",
        "value_a": PAYLOAD_A, "value_b": PAYLOAD_B_PK,
        "replica_a_id": "a", "replica_b_id": "b",
    }
    state.conflicts[record["conflict_id"]] = record
    state.replicas = {"a": {"db_path": str(a)}, "b": {"db_path": str(b)}}
    return state, record, a, b


def _resolve(conflict_id, mode, custom=None):
    return routes_conflicts.resolve_conflict(
        ConflictResolveRequest(conflict_id=conflict_id, resolution_mode=mode, custom_value=custom)
    )


@pytest.mark.parametrize(("mode", "expected"), [("pick_a", PAYLOAD_A), ("pick_b", PAYLOAD_B_PK)])
def test_pk_collision_pick_preserves_both_snapshots_and_audits_resolution(resolution_case, mode, expected):
    state, record, a, b = resolution_case
    original_a, original_b = dict(record["value_a"]), dict(record["value_b"])

    response = _resolve("pk-conflict", mode)

    assert response["status"] == "resolved"
    assert _rows(a) == _rows(b) == [(expected["id"], expected["code"], expected["value"])]
    persisted = state.get_conflict("pk-conflict")
    assert persisted["value_a"] == original_a and persisted["value_b"] == original_b
    assert persisted["status"] == "resolved"
    log_a, log_b = _resolution_logs(a), _resolution_logs(b)
    assert len(log_a) == len(log_b) == 1
    assert log_a[0][:3] == log_b[0][:3]
    assert json.loads(log_a[0][4])["value"] == expected
    restarted = AppState()
    restarted.load()
    assert restarted.get_conflict("pk-conflict")["resolution_operation"]["operation_id"] == log_a[0][0]


def test_secondary_unique_pick_a_removes_losing_row_explicitly_and_custom_replaces(resolution_case):
    state, record, a, b = resolution_case
    record.update({"conflict_id": "unique-conflict", "conflict_type": "UNIQUE_COLLISION",
                   "row_id": "1 vs 2", "value_b": PAYLOAD_B_UNIQUE})
    state.conflicts["unique-conflict"] = record
    _db_rebuild_b = b
    with sqlite3.connect(_db_rebuild_b) as conn:
        conn.execute("DELETE FROM items")
        conn.execute("INSERT INTO items VALUES (2, 'shared', 'B')")
        conn.commit()

    response = _resolve("unique-conflict", "pick_a")
    assert response["status"] == "resolved"
    assert _rows(a) == _rows(b) == [(1, "shared", "A")]
    assert state.get_conflict("unique-conflict")["value_b"] == PAYLOAD_B_UNIQUE

    # A fresh secondary-UNIQUE collision can be explicitly resolved to a replacement.
    with sqlite3.connect(a) as conn:
        conn.execute("DELETE FROM items")
        conn.execute("INSERT INTO items VALUES (1, 'shared', 'A')")
        conn.commit()
    with sqlite3.connect(b) as conn:
        conn.execute("DELETE FROM items")
        conn.execute("INSERT INTO items VALUES (2, 'shared', 'B')")
        conn.commit()
    record2 = dict(record, conflict_id="custom-conflict", status="flagged")
    state.conflicts["custom-conflict"] = record2
    replacement = {"id": 3, "code": "replacement", "value": "manual"}
    _resolve("custom-conflict", "custom", replacement)
    assert _rows(a) == _rows(b) == [(3, "replacement", "manual")]


def test_custom_payload_must_be_complete_and_unique_violation_rolls_back(resolution_case):
    state, record, a, b = resolution_case
    with pytest.raises(HTTPException) as exc:
        _resolve("pk-conflict", "custom", {"id": 1, "code": "shared"})
    assert exc.value.status_code == 409
    assert _rows(a) == [(1, "shared", "A")]
    assert _rows(b) == [(1, "shared", "B")]
    assert not _resolution_logs(a) and not _resolution_logs(b)
    assert state.get_conflict("pk-conflict")["status"] == "flagged"

    # Unrelated row owns this UNIQUE value; replacement must not overwrite it.
    with sqlite3.connect(a) as conn:
        conn.execute("INSERT INTO items VALUES (9, 'reserved', 'untouched')")
        conn.commit()
    with sqlite3.connect(b) as conn:
        conn.execute("INSERT INTO items VALUES (9, 'reserved', 'untouched')")
        conn.commit()
    replacement = {"id": 3, "code": "reserved", "value": "replacement"}
    with pytest.raises(HTTPException, match="rolled back"):
        _resolve("pk-conflict", "custom", replacement)
    assert _rows(a) == [(1, "shared", "A"), (9, "reserved", "untouched")]
    assert _rows(b) == [(1, "shared", "B"), (9, "reserved", "untouched")]
    assert not _resolution_logs(a) and not _resolution_logs(b)


def test_second_replica_failure_rolls_back_and_retry_is_idempotent(resolution_case):
    state, record, a, b = resolution_case
    with sqlite3.connect(b) as conn:
        conn.execute(
            "CREATE TRIGGER reject_resolution BEFORE INSERT ON items "
            "WHEN NEW.value='A' BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        conn.commit()
    with pytest.raises(HTTPException):
        _resolve("pk-conflict", "pick_a")
    assert _rows(a) == [(1, "shared", "A")]
    assert _rows(b) == [(1, "shared", "B")]
    assert not _resolution_logs(a) and not _resolution_logs(b)
    assert record["status"] == "flagged"

    with sqlite3.connect(b) as conn:
        conn.execute("DROP TRIGGER reject_resolution")
        conn.commit()
    first = _resolve("pk-conflict", "pick_a")
    second = _resolve("pk-conflict", "pick_a")
    assert first["status"] == second["status"] == "resolved"
    assert second["conflict"]["resolution_operation"]["replayed"] is True
    assert _rows(a) == _rows(b) == [(1, "shared", "A")]
    assert len(_resolution_logs(a)) == len(_resolution_logs(b)) == 1
    assert _resolution_logs(a)[0][:3] == _resolution_logs(b)[0][:3]


def test_registry_write_failure_recovers_from_durable_resolution_receipt(resolution_case, monkeypatch):
    state, record, a, b = resolution_case
    state.save()  # Persist the pending conflict and replica paths before resolution.
    original_store = state.store_conflict

    def fail_once(conflict_id, value):
        if value.get("status") == "resolved":
            raise OSError("injected registry write failure")
        original_store(conflict_id, value)

    monkeypatch.setattr(state, "store_conflict", fail_once)
    with pytest.raises(OSError, match="registry write failure"):
        _resolve("pk-conflict", "pick_a")
    assert _rows(a) == _rows(b) == [(1, "shared", "A")]
    assert len(_resolution_logs(a)) == len(_resolution_logs(b)) == 1

    # Simulate process restart: the durable registry still says pending, while
    # the attached-database receipt proves the row operation already committed.
    restarted = AppState()
    restarted.load()
    assert restarted.get_conflict("pk-conflict")["status"] == "flagged"
    monkeypatch.setattr(routes_conflicts, "app_state", restarted)
    response = _resolve("pk-conflict", "pick_a")
    assert response["status"] == "resolved"
    assert response["conflict"]["resolution_operation"]["replayed"] is True
    assert len(_resolution_logs(a)) == len(_resolution_logs(b)) == 1


def test_registry_replace_failure_preserves_previous_restart_state(resolution_case, monkeypatch):
    import backend.api.state as state_module

    state, record, _a, _b = resolution_case
    state.save()
    registry_before = state_module.REGISTRY_FILE.read_text(encoding="utf-8")
    state.conflicts[record["conflict_id"]]["status"] = "resolved"
    monkeypatch.setattr(state_module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        state.save()

    assert state_module.REGISTRY_FILE.read_text(encoding="utf-8") == registry_before
    assert not list(state_module.DATA_DIR.glob(".registry.json.*.tmp"))
    restarted = AppState()
    restarted.load()
    assert restarted.get_conflict("pk-conflict")["status"] == "flagged"


def test_conflict_changed_after_detection_is_refused_without_overwrite(resolution_case):
    _state, _record, a, b = resolution_case
    with sqlite3.connect(b) as conn:
        conn.execute("UPDATE items SET value='local edit' WHERE id=1")
        conn.commit()
    with pytest.raises(HTTPException, match="changed since conflict detection"):
        _resolve("pk-conflict", "pick_a")
    assert _rows(a) == [(1, "shared", "A")]
    assert _rows(b) == [(1, "shared", "local edit")]
    assert not _resolution_logs(a) and not _resolution_logs(b)


def test_missing_collision_rows_are_not_resurrected_by_stale_resolution(resolution_case):
    _state, _record, a, b = resolution_case
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            conn.execute("DELETE FROM items")
            conn.commit()
    with pytest.raises(HTTPException, match="no longer present"):
        _resolve("pk-conflict", "pick_a")
    assert _rows(a) == _rows(b) == []
    assert not _resolution_logs(a) and not _resolution_logs(b)


def test_referenced_collision_row_is_refused_until_dependent_data_semantics_exist(resolution_case):
    _state, record, a, b = resolution_case
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE child (id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id))")
            conn.execute("INSERT INTO child VALUES (1, 1)")
            conn.commit()
    with pytest.raises(HTTPException, match="references a participant row"):
        _resolve("pk-conflict", "pick_a")
    assert _rows(a) == [(1, "shared", "A")]
    assert _rows(b) == [(1, "shared", "B")]
    assert not _resolution_logs(a) and not _resolution_logs(b)
    for path in (a, b):
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT item_id FROM child").fetchall() == [(1,)]
