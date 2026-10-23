"""Seed route safety and workload-fixture smoke checks without HTTP lifespan."""

import sqlite3

import pytest
from fastapi import HTTPException

from backend.api.models import SeedRequest
from backend.api import routes_seed


class InMemoryAppState:
    def __init__(self):
        self.databases = {}
        self.replicas = {}
        self.policies = {}
        self.registry_load_error = None

    def get_db(self, db_id):
        return self.databases.get(db_id)

    def register_db(self, db_id, **info):
        self.databases[db_id] = {"id": db_id, **info}

    def register_replica(self, replica_id, **info):
        self.replicas[replica_id] = {"replica_id": replica_id, **info}

    def set_policy(self, db_id, table, column, policy):
        self.policies[(db_id, table, column)] = policy


def test_inventory_seed_maps_replica_ids_and_refuses_repeat_seed(tmp_path, monkeypatch):
    data_dir = tmp_path / "isolated-demo"
    state = InMemoryAppState()
    monkeypatch.setattr(routes_seed, "DATA_DIR", data_dir)
    monkeypatch.setattr(routes_seed, "app_state", state)

    result = routes_seed.seed_workload(SeedRequest(workload="inventory"))
    assert result["status"] == "seeded"
    assert result["workloads_created"][0]["replicas"] == [
        "inventory_device_a", "inventory_device_b", "inventory_device_c"
    ]

    with sqlite3.connect(data_dir / "inventory" / "inventory_device_a.db") as conn:
        assert conn.execute("SELECT quantity FROM products WHERE id=1").fetchone()[0] == 115
    with sqlite3.connect(data_dir / "inventory" / "inventory_device_b.db") as conn:
        assert conn.execute("SELECT quantity FROM products WHERE id=1").fetchone()[0] == 120
    with sqlite3.connect(data_dir / "inventory" / "inventory.db") as conn:
        assert conn.execute("SELECT quantity FROM products WHERE id=1").fetchone()[0] == 100

    with pytest.raises(HTTPException) as exc:
        routes_seed.seed_workload(SeedRequest(workload="inventory"))
    assert exc.value.status_code == 409
    assert "fresh SEMANTICSYNC_DATA_DIR" in exc.value.detail

    with sqlite3.connect(data_dir / "inventory" / "inventory_device_a.db") as conn:
        assert conn.execute("SELECT quantity FROM products WHERE id=1").fetchone()[0] == 115


def test_seed_rejects_unknown_workload_before_creating_files(tmp_path, monkeypatch):
    data_dir = tmp_path / "isolated-demo"
    monkeypatch.setattr(routes_seed, "DATA_DIR", data_dir)
    monkeypatch.setattr(routes_seed, "app_state", InMemoryAppState())

    with pytest.raises(HTTPException) as exc:
        routes_seed.seed_workload(SeedRequest(workload="unknown"))

    assert exc.value.status_code == 400
    assert not data_dir.exists()


def test_all_seeded_workloads_use_route_replica_ids_for_fixture_divergence(tmp_path, monkeypatch):
    data_dir = tmp_path / "isolated-demo"
    monkeypatch.setattr(routes_seed, "DATA_DIR", data_dir)
    monkeypatch.setattr(routes_seed, "app_state", InMemoryAppState())

    result = routes_seed.seed_workload(SeedRequest(workload="all"))
    assert len(result["workloads_created"]) == 3

    with sqlite3.connect(data_dir / "notes" / "notes_device_a.db") as conn:
        assert conn.execute("SELECT edit_count FROM notes WHERE id=1").fetchone()[0] == 2
    with sqlite3.connect(data_dir / "notes" / "notes_device_b.db") as conn:
        assert conn.execute("SELECT edit_count FROM notes WHERE id=1").fetchone()[0] == 3
    with sqlite3.connect(data_dir / "health" / "health_device_a.db") as conn:
        assert conn.execute("SELECT heart_rate FROM patients WHERE id=1").fetchone()[0] == 75
    with sqlite3.connect(data_dir / "health" / "health_device_b.db") as conn:
        assert conn.execute("SELECT heart_rate,blood_type FROM patients WHERE id=1").fetchone() == (69, "B+")


def test_seed_fails_closed_when_registry_state_is_untrusted(tmp_path, monkeypatch):
    data_dir = tmp_path / "isolated-demo"
    state = InMemoryAppState()
    state.registry_load_error = "registry JSON is corrupt"
    monkeypatch.setattr(routes_seed, "DATA_DIR", data_dir)
    monkeypatch.setattr(routes_seed, "app_state", state)

    with pytest.raises(HTTPException) as exc:
        routes_seed.seed_workload(SeedRequest(workload="all"))

    assert exc.value.status_code == 409
    assert "state is not trusted" in exc.value.detail
    assert not data_dir.exists()
