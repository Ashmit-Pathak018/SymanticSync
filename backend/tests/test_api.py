"""
test_api.py
===========
Pytest integration tests verifying all /api/v1 endpoints.
"""

import pytest
from starlette.testclient import TestClient
from backend.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_and_root(client):
    r1 = client.get("/api/v1/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"

    r2 = client.get("/")
    assert r2.status_code == 200
    assert "SemanticSync" in r2.json()["name"]


def test_seed_and_list_databases(client):
    r_seed = client.post("/api/v1/seed", json={"workload": "all"})
    assert r_seed.status_code == 200
    assert r_seed.json()["status"] == "seeded"

    r_dbs = client.get("/api/v1/databases")
    assert r_dbs.status_code == 200
    dbs = r_dbs.json()
    assert len(dbs) >= 3

    # Check inventory schema
    r_schema = client.get("/api/v1/databases/db_inventory/schema")
    assert r_schema.status_code == 200
    schema = r_schema.json()
    assert schema["db_id"] == "db_inventory"
    table_names = [t["table_name"] for t in schema["tables"]]
    assert "products" in table_names


def test_validate_policy_endpoint(client):
    # Valid
    r_valid = client.post(
        "/api/v1/validate-policy",
        json={"table": "products", "column": "quantity", "policy": "SUM", "normalized_type": "INTEGER"},
    )
    assert r_valid.status_code == 200
    assert r_valid.json()["valid"] is True

    # Incompatible (AVG on TEXT)
    r_invalid = client.post(
        "/api/v1/validate-policy",
        json={"table": "products", "column": "description", "policy": "AVG", "normalized_type": "TEXT"},
    )
    assert r_invalid.status_code == 200
    assert r_invalid.json()["valid"] is False
    assert r_invalid.json()["error_code"] == "TYPE_INCOMPATIBLE"


def test_query_endpoint(client):
    r_q = client.post(
        "/api/v1/query",
        json={"db_id": "db_inventory", "sql": "SELECT id, sku, quantity FROM products WHERE id = 1"},
    )
    assert r_q.status_code == 200
    res = r_q.json()
    assert res["columns"] == ["id", "sku", "quantity"]
    assert len(res["rows"]) == 1
    assert res["rows"][0][0] == 1


def test_sync_status_endpoint(client):
    r_sync = client.get("/api/v1/sync/status")
    assert r_sync.status_code == 200
    data = r_sync.json()
    assert data["status"] == "ready"
    assert data["registered_databases"] >= 3


def test_benchmark_endpoint(client):
    r_bm = client.post("/api/v1/benchmark/run", json={"workload": "inventory"})
    assert r_bm.status_code == 200
    metrics = r_bm.json()
    assert metrics["workload"] == "inventory"
    assert metrics["semantic_sync_scr"] >= 90.0
    assert metrics["total_conflicts_evaluated"] >= 3


def test_conflicts_resolve_api_endpoint(client, tmp_path, monkeypatch):
    import sqlite3
    from backend.api.state import app_state

    db_a = tmp_path / "rep_a.db"
    db_b = tmp_path / "rep_b.db"
    for p, val in ((db_a, 80), (db_b, 60)):
        with sqlite3.connect(p) as conn:
            conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
            conn.execute("INSERT INTO counters VALUES (1, ?)", (val,))
            conn.commit()

    monkeypatch.setattr(app_state, "get_replica_path", lambda rid: str(db_a if rid == "a" else db_b if rid == "b" else None))
    monkeypatch.setattr(app_state, "get_policy", lambda db, tbl, col: "BOUNDED_SUM[min=0,max=100]")

    conflict_id = "api-conflict-test-1"
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
        "policy": "BOUNDED_SUM[min=0,max=100]",
    }
    app_state.store_conflict(conflict_id, record)

    # A. Successful auto resolution: 50 + 30 + 10 = 90
    resp = client.post("/api/v1/conflicts/resolve", json={
        "conflict_id": conflict_id,
        "resolution_mode": "auto",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["result"] == 90
    assert data["policy"] == "BOUNDED_SUM[min=0,max=100]"
    assert "explanation" in data
    assert isinstance(data["conflict"], dict)
    assert data["conflict"]["status"] == "resolved"
    with sqlite3.connect(db_a) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == 90
    with sqlite3.connect(db_b) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == 90

    # B. Out-of-bounds auto resolution remains flagged
    conflict_overflow = "api-conflict-overflow"
    record_overflow = {
        "conflict_id": conflict_overflow,
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
        "policy": "BOUNDED_SUM[min=0,max=100]",
    }
    app_state.store_conflict(conflict_overflow, record_overflow)
    resp_of = client.post("/api/v1/conflicts/resolve", json={
        "conflict_id": conflict_overflow,
        "resolution_mode": "auto",
    })
    assert resp_of.status_code == 200
    data_of = resp_of.json()
    assert data_of["status"] == "flagged"
    assert "Unsafe overflow" in data_of["explanation"]
    assert data_of["conflict"]["status"] == "flagged"
    # Both replicas' database values remain unchanged (still 90 from the previous resolution)
    with sqlite3.connect(db_a) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == 90
    with sqlite3.connect(db_b) as conn:
        assert conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0] == 90

    # C. Status code: 404 for unknown conflict
    resp_404 = client.post("/api/v1/conflicts/resolve", json={
        "conflict_id": "nonexistent-id",
        "resolution_mode": "auto",
    })
    assert resp_404.status_code == 404

    # D. Status code: 400 for invalid resolution mode
    resp_400_mode = client.post("/api/v1/conflicts/resolve", json={
        "conflict_id": conflict_id,
        "resolution_mode": "unsupported_mode",
    })
    assert resp_400_mode.status_code == 400

    # E. Status code: 400 for auto mode on INSERT collision
    conflict_insert = "api-conflict-insert"
    record_insert = {
        "conflict_id": conflict_insert,
        "db_id": "test_db",
        "table": "counters",
        "row_id": 2,
        "column": "*",
        "conflict_type": "INSERT_INSERT",
        "replica_a_id": "a",
        "replica_b_id": "b",
        "status": "pending",
    }
    app_state.store_conflict(conflict_insert, record_insert)
    resp_400_insert = client.post("/api/v1/conflicts/resolve", json={
        "conflict_id": conflict_insert,
        "resolution_mode": "auto",
    })
    assert resp_400_insert.status_code == 400
    assert "INSERT collisions require explicit" in resp_400_insert.json()["detail"]


def test_state_save_retry_exhaustion_unrelated_errors_and_cleanup(monkeypatch):
    import os
    from backend.api.state import app_state

    # 1. Retry exhaustion: PermissionError raised 10 times -> re-raises PermissionError
    call_count = 0
    def mock_replace_perm(src, dst):
        nonlocal call_count
        call_count += 1
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", mock_replace_perm)
    with pytest.raises(PermissionError, match="locked"):
        app_state.save()
    assert call_count == 10

    # 2. Unrelated error: OSError raised immediately on first attempt without retrying
    unrelated_count = 0
    def mock_replace_oserror(src, dst):
        nonlocal unrelated_count
        unrelated_count += 1
        raise OSError("Disk full")

    monkeypatch.setattr(os, "replace", mock_replace_oserror)
    with pytest.raises(OSError, match="Disk full"):
        app_state.save()
    assert unrelated_count == 1

    # 3. Cleanup failure does not mask original error
    def mock_replace_perm2(src, dst):
        raise PermissionError("locked again")

    def mock_unlink_fail(path):
        raise OSError("unlink failed")

    monkeypatch.setattr(os, "replace", mock_replace_perm2)
    monkeypatch.setattr(os, "unlink", mock_unlink_fail)
    with pytest.raises(PermissionError, match="locked again"):
        app_state.save()
