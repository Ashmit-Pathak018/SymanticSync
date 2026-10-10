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
