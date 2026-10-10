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
