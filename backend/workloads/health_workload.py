"""
health_workload.py
==================
Illustrative healthcare benchmark workload.

IMPORTANT: The SemanticSync **engine layer** remains 100% domain-agnostic.
This workload file exists purely to demonstrate that the generic engine
policies (AVG, APPEND, REJECT) are sufficient to handle healthcare-adjacent
scenarios without any domain-specific code in the core.

Schema
------
``patients(id INTEGER PK, name TEXT, blood_type TEXT, heart_rate INTEGER,
dosage_mg REAL, clinical_notes TEXT)``

Policies
--------
* ``heart_rate``    → AVG    (average concurrent sensor readings)
* ``dosage_mg``     → AVG    (average concurrent dosage records)
* ``clinical_notes``→ APPEND (preserve all concurrent observations)
* ``blood_type``    → REJECT  (must never be silently overwritten)
* ``name``          → LWW    (most recent legal name update wins)

Ground-truth conflicts
----------------------
Three conflict scenarios covering AVG, APPEND, and REJECT.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.workloads.base_workload import BaseWorkload


class HealthWorkload(BaseWorkload):
    """Illustrative healthcare benchmark workload (engine stays domain-agnostic)."""

    name = "health"
    description = (
        "Healthcare-adjacent benchmark: averaged readings (AVG), "
        "concurrent clinical notes (APPEND), and blood-type protection (REJECT). "
        "Engine layer contains zero domain-specific code."
    )

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id              INTEGER PRIMARY KEY,
                name            TEXT,
                blood_type      TEXT,
                heart_rate      INTEGER,
                dosage_mg       REAL,
                clinical_notes  TEXT
            );
            """
        )

    # ------------------------------------------------------------------
    # Seed data (3 patient records)
    # ------------------------------------------------------------------

    def seed_base_data(self, conn: sqlite3.Connection) -> None:
        rows = [
            (1, "Pat. Alpha",  "A+",  72, 10.0, "Initial assessment normal."),
            (2, "Pat. Beta",   "B-",  88, 5.5,  "Mild hypertension noted."),
            (3, "Pat. Gamma",  "O+",  65, 20.0, "Post-op follow-up scheduled."),
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO patients "
            "(id, name, blood_type, heart_rate, dosage_mg, clinical_notes) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            rows,
        )

    # ------------------------------------------------------------------
    # Policy assignments
    # ------------------------------------------------------------------

    def get_policy_assignments(self) -> list[dict[str, str]]:
        return [
            {"table": "patients", "column": "heart_rate",     "policy": "AVG"},
            {"table": "patients", "column": "dosage_mg",      "policy": "AVG"},
            {"table": "patients", "column": "clinical_notes", "policy": "APPEND"},
            {"table": "patients", "column": "blood_type",     "policy": "REJECT"},
            {"table": "patients", "column": "name",           "policy": "LWW"},
        ]

    # ------------------------------------------------------------------
    # Ground-truth conflict scenarios
    # ------------------------------------------------------------------

    def get_ground_truth_conflicts(self) -> list[dict[str, Any]]:
        return [
            # ── Scenario 1: AVG on heart_rate ────────────────────────
            # Nurse station A recorded 75 bpm; nurse station B recorded 69 bpm.
            # Semantic (AVG): (75 + 69) / 2 = 72.0
            # Baseline (LWW): whichever timestamp wins (one reading discarded)
            {
                "table":  "patients",
                "row_id": 1,
                "column": "heart_rate",
                "base_value":  72,
                "value_a":     75,
                "value_b":     69,
                "expected_semantic_result":  72.0,
                "expected_baseline_result":  "LWW: 75 or 69 (one reading discarded)",
            },
            # ── Scenario 2: APPEND on clinical_notes ─────────────────
            # Two clinicians added concurrent observations while offline.
            # Semantic (APPEND): both observations preserved
            # Baseline (LWW): one clinician's note silently lost
            {
                "table":  "patients",
                "row_id": 1,
                "column": "clinical_notes",
                "base_value": "Initial assessment normal.",
                "value_a":    "Initial assessment normal. Clinician A: BP 120/80.",
                "value_b":    "Initial assessment normal. Clinician B: SpO2 98%.",
                "expected_semantic_result": (
                    "Initial assessment normal. Clinician A: BP 120/80.; "
                    "Initial assessment normal. Clinician B: SpO2 98%."
                ),
                "expected_baseline_result": "LWW: one clinician's note lost",
            },
            # ── Scenario 3: REJECT on blood_type ─────────────────────
            # Device B attempted to change blood type (possible data-entry error).
            # Semantic (REJECT): flagged for human verification
            # Baseline (LWW): silent overwrite with potentially incorrect value
            {
                "table":  "patients",
                "row_id": 1,
                "column": "blood_type",
                "base_value":  "A+",
                "value_a":     "A+",
                "value_b":     "B+",
                "expected_semantic_result":  "FLAGGED",
                "expected_baseline_result":  "LWW: blood type silently overwritten",
            },
        ]


def seed(base_path: str, replica_paths: dict[str, str]) -> dict[str, Any]:
    con = sqlite3.connect(base_path, check_same_thread=False)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id              INTEGER PRIMARY KEY,
            name            TEXT,
            blood_type      TEXT,
            heart_rate      INTEGER,
            dosage_mg       REAL,
            clinical_notes  TEXT
        );
        """
    )
    rows = [
        (1, "Pat. Alpha",  "A+",  72, 10.0, "Initial assessment normal."),
        (2, "Pat. Beta",   "B-",  88, 5.5,  "Mild hypertension noted."),
        (3, "Pat. Gamma",  "O+",  65, 20.0, "Post-op follow-up scheduled."),
    ]
    con.executemany(
        "INSERT OR REPLACE INTO patients (id, name, blood_type, heart_rate, dosage_mg, clinical_notes) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        rows,
    )
    con.commit()
    con.close()

    for replica_id, path in replica_paths.items():
        con_r = sqlite3.connect(path, check_same_thread=False)
        con_r.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id              INTEGER PRIMARY KEY,
                name            TEXT,
                blood_type      TEXT,
                heart_rate      INTEGER,
                dosage_mg       REAL,
                clinical_notes  TEXT
            );
            """
        )
        con_r.executemany(
            "INSERT OR REPLACE INTO patients (id, name, blood_type, heart_rate, dosage_mg, clinical_notes) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            rows,
        )
        if replica_id == "device_a" or replica_id.endswith("_device_a"):
            con_r.execute("UPDATE patients SET heart_rate = 75, clinical_notes = 'Initial assessment normal. Clinician A: BP 120/80.' WHERE id = 1")
        elif replica_id == "device_b" or replica_id.endswith("_device_b"):
            con_r.execute("UPDATE patients SET heart_rate = 69, clinical_notes = 'Initial assessment normal. Clinician B: SpO2 98%.', blood_type = 'B+' WHERE id = 1")
        con_r.commit()
        con_r.close()

    return {
        "workload": "health",
        "base_rows": len(rows),
        "replicas_seeded": list(replica_paths.keys()),
        "suggested_policies": [
            {"table": "patients", "column": "heart_rate",     "policy": "AVG"},
            {"table": "patients", "column": "dosage_mg",      "policy": "AVG"},
            {"table": "patients", "column": "clinical_notes", "policy": "APPEND"},
            {"table": "patients", "column": "blood_type",     "policy": "REJECT"},
            {"table": "patients", "column": "name",           "policy": "LWW"},
        ],
    }

