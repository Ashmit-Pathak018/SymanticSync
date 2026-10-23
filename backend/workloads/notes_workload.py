"""
backend/workloads/notes_workload.py
─────────────────────────────────────
Notes / document collaboration workload: bodies (APPEND), edit counters (SUM), authors (REJECT/LWW).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.workloads.base_workload import BaseWorkload

WORKLOAD_NAME = "notes"

_CREATE_NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL DEFAULT '',
    author      TEXT    NOT NULL,
    edit_count  INTEGER NOT NULL DEFAULT 0,
    tags        TEXT    DEFAULT ''
);
"""

_BASE_ROWS = [
    (1, "Project Kickoff",    "Initial meeting notes.",   "alice", 1, "meeting,planning"),
    (2, "Architecture Draft", "High-level design notes.", "bob",   1, "design"),
    (3, "Release Checklist",  "Items for v1 launch.",     "carol", 1, "ops,release"),
]

SUGGESTED_POLICIES = [
    {"table": "notes", "column": "body",       "policy": "APPEND"},
    {"table": "notes", "column": "edit_count", "policy": "SUM"},
    {"table": "notes", "column": "author",     "policy": "REJECT"},
    {"table": "notes", "column": "title",      "policy": "LWW"},
    {"table": "notes", "column": "tags",       "policy": "APPEND"},
]


class NotesWorkload(BaseWorkload):
    name = "notes"
    description = "Collaborative document editing: text appends, additive edit counts, and conflict inspection."

    def create_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(_CREATE_NOTES)

    def seed_base_data(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT OR REPLACE INTO notes (id, title, body, author, edit_count, tags) VALUES (?, ?, ?, ?, ?, ?)",
            _BASE_ROWS,
        )

    def get_policy_assignments(self) -> list[dict[str, str]]:
        return list(SUGGESTED_POLICIES)

    def get_ground_truth_conflicts(self) -> list[dict[str, Any]]:
        return [
            {
                "table": "notes",
                "row_id": 1,
                "column": "body",
                "base_value": "Initial meeting notes.",
                "value_a": "Initial meeting notes. Alice action items.",
                "value_b": "Initial meeting notes. Bob risk register.",
                "expected_semantic_result": "Initial meeting notes. Alice action items.; Initial meeting notes. Bob risk register.",
                "expected_baseline_result": "Initial meeting notes. Bob risk register.",
            },
            {
                "table": "notes",
                "row_id": 1,
                "column": "edit_count",
                "base_value": 1,
                "value_a": 2,  # +1
                "value_b": 3,  # +2
                "expected_semantic_result": 4,  # 1 + 1 + 2
                "expected_baseline_result": 3,
            },
            {
                "table": "notes",
                "row_id": 1,
                "column": "author",
                "base_value": "alice",
                "value_a": "alice_prime",
                "value_b": "bob",
                "expected_semantic_result": "FLAGGED",  # REJECT => flagged
                "expected_baseline_result": "bob",
            },
        ]


def seed(base_path: str, replica_paths: dict[str, str]) -> dict[str, Any]:
    con = sqlite3.connect(base_path, check_same_thread=False)
    con.execute(_CREATE_NOTES)
    con.executemany(
        "INSERT OR REPLACE INTO notes (id, title, body, author, edit_count, tags) VALUES (?, ?, ?, ?, ?, ?)",
        _BASE_ROWS,
    )
    con.commit()
    con.close()

    for replica_id, path in replica_paths.items():
        con_r = sqlite3.connect(path, check_same_thread=False)
        con_r.execute(_CREATE_NOTES)
        con_r.executemany(
            "INSERT OR REPLACE INTO notes (id, title, body, author, edit_count, tags) VALUES (?, ?, ?, ?, ?, ?)",
            _BASE_ROWS,
        )
        if replica_id == "device_a" or replica_id.endswith("_device_a"):
            con_r.execute("UPDATE notes SET edit_count = 2, body = 'Initial meeting notes. Alice action items.' WHERE id = 1")
        elif replica_id == "device_b" or replica_id.endswith("_device_b"):
            con_r.execute("UPDATE notes SET edit_count = 3, body = 'Initial meeting notes. Bob risk register.' WHERE id = 1")
        con_r.commit()
        con_r.close()

    return {
        "workload": WORKLOAD_NAME,
        "base_rows": len(_BASE_ROWS),
        "replicas_seeded": list(replica_paths.keys()),
        "suggested_policies": SUGGESTED_POLICIES,
    }
