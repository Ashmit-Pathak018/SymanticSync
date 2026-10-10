"""
backend/workloads/inventory_workload.py
─────────────────────────────────────────
Inventory benchmark workload: stock counts, descriptions, skus, prices.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.workloads.base_workload import BaseWorkload

WORKLOAD_NAME = "inventory"

_CREATE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY,
    sku           TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    quantity      INTEGER NOT NULL DEFAULT 0,
    price         REAL    NOT NULL DEFAULT 0.0,
    description   TEXT    DEFAULT '',
    critical_flag INTEGER DEFAULT 0
);
"""

_BASE_ROWS = [
    (1, "SKU-001", "Widget Alpha",   100, 9.99,  "Original desc",  0),
    (2, "SKU-002", "Gadget Beta",     50, 24.99, "Warehouse B",    0),
    (3, "SKU-003", "Doohickey Gamma", 200, 4.49, "Fast mover",     1),
]

SUGGESTED_POLICIES = [
    {"table": "products", "column": "quantity",      "policy": "SUM"},
    {"table": "products", "column": "description",   "policy": "APPEND"},
    {"table": "products", "column": "price",         "policy": "AVG"},
    {"table": "products", "column": "name",          "policy": "LWW"},
    {"table": "products", "column": "sku",           "policy": "REJECT"},
    {"table": "products", "column": "critical_flag", "policy": "REJECT"},
]


class InventoryWorkload(BaseWorkload):
    name = "inventory"
    description = "Inventory management: additive stock counts, appended notes, and immutable SKU constraints."

    def create_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(_CREATE_PRODUCTS)

    def seed_base_data(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT OR REPLACE INTO products (id, sku, name, quantity, price, description, critical_flag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            _BASE_ROWS,
        )

    def get_policy_assignments(self) -> list[dict[str, str]]:
        return list(SUGGESTED_POLICIES)

    def get_ground_truth_conflicts(self) -> list[dict[str, Any]]:
        return [
            {
                "table": "products",
                "row_id": 1,
                "column": "quantity",
                "base_value": 100,
                "value_a": 115,  # +15
                "value_b": 120,  # +20
                "expected_semantic_result": 135,
                "expected_baseline_result": 120,  # LWW picks one
            },
            {
                "table": "products",
                "row_id": 1,
                "column": "description",
                "base_value": "Original desc",
                "value_a": "Original desc; Restocked by device_a",
                "value_b": "Original desc; Restocked by device_b",
                "expected_semantic_result": "Original desc; Restocked by device_a; Original desc; Restocked by device_b",
                "expected_baseline_result": "Original desc; Restocked by device_b",
            },
            {
                "table": "products",
                "row_id": 1,
                "column": "sku",
                "base_value": "SKU-001",
                "value_a": "SKU-001-A",
                "value_b": "SKU-001-B",
                "expected_semantic_result": "FLAGGED",  # REJECT => flagged
                "expected_baseline_result": "SKU-001-B",
            },
        ]


def seed(base_path: str, replica_paths: dict[str, str]) -> dict[str, Any]:
    con = sqlite3.connect(base_path, check_same_thread=False)
    con.execute(_CREATE_PRODUCTS)
    con.executemany(
        "INSERT OR REPLACE INTO products (id, sku, name, quantity, price, description, critical_flag) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        _BASE_ROWS,
    )
    con.commit()
    con.close()

    for replica_id, path in replica_paths.items():
        con_r = sqlite3.connect(path, check_same_thread=False)
        con_r.execute(_CREATE_PRODUCTS)
        con_r.executemany(
            "INSERT OR REPLACE INTO products (id, sku, name, quantity, price, description, critical_flag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            _BASE_ROWS,
        )
        if replica_id == "device_a":
            con_r.execute("UPDATE products SET quantity = 115, description = 'Original desc; Restocked by device_a' WHERE id = 1")
        elif replica_id == "device_b":
            con_r.execute("UPDATE products SET quantity = 120, description = 'Original desc; Restocked by device_b' WHERE id = 1")
        con_r.commit()
        con_r.close()

    return {
        "workload": WORKLOAD_NAME,
        "base_rows": len(_BASE_ROWS),
        "replicas_seeded": list(replica_paths.keys()),
        "suggested_policies": SUGGESTED_POLICIES,
    }
