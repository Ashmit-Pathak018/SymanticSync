"""
test_benchmark.py
=================
Pytest tests for benchmark workloads (Inventory, Notes, Healthcare) and metrics.
"""

from pathlib import Path
import pytest

from backend.workloads.inventory_workload import InventoryWorkload
from backend.workloads.notes_workload import NotesWorkload
from backend.workloads.health_workload import HealthWorkload


def test_inventory_workload_setup(tmp_path: Path):
    workload = InventoryWorkload(data_dir=str(tmp_path))
    info = workload.setup()
    assert "db_id" in info
    assert "base_path" in info
    assert "replicas" in info
    assert len(info["replicas"]) >= 2

    conflicts = workload.get_ground_truth_conflicts()
    assert len(conflicts) >= 3


def test_notes_workload_setup(tmp_path: Path):
    workload = NotesWorkload(data_dir=str(tmp_path))
    info = workload.setup()
    assert "db_id" in info
    assert "base_path" in info
    assert len(info["replicas"]) >= 2

    policies = workload.get_policy_assignments()
    assert any(p["policy"] == "APPEND" for p in policies)


def test_health_workload_setup(tmp_path: Path):
    workload = HealthWorkload(data_dir=str(tmp_path))
    info = workload.setup()
    assert "db_id" in info
    assert "base_path" in info

    conflicts = workload.get_ground_truth_conflicts()
    assert any(c["column"] == "heart_rate" for c in conflicts)
