"""
base_workload.py
================
Abstract base class for all SemanticSync benchmark workloads.

A *workload* encapsulates:
* A SQLite schema definition.
* Seed data that represents a realistic starting state.
* Policy assignments: ``{table, column, policy}`` triples.
* Ground-truth conflict scenarios used for benchmarking SCR (Semantic
  Correctness Rate).

Subclasses must implement the four abstract methods; the :meth:`setup`
template method handles database creation, replication, and controlled
divergence injection automatically.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class BaseWorkload(ABC):
    """Abstract workload for SemanticSync benchmark evaluation.

    Attributes
    ----------
    name:
        Short identifier for the workload (class-level).
    description:
        Human-readable summary of the workload (class-level).
    """

    name: str
    description: str

    def __init__(self, data_dir: str | Path | None = None) -> None:
        if data_dir is None:
            data_dir = os.environ.get("SEMANTICSYNC_DATA_DIR", str(DEFAULT_DATA_DIR))
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by every workload
    # ------------------------------------------------------------------

    @abstractmethod
    def create_schema(self, conn: sqlite3.Connection) -> None:
        """Create table(s) for this workload in *conn*.

        Must use ``CREATE TABLE IF NOT EXISTS`` with parameterised DDL.
        No domain-specific logic should bleed into the engine layer.
        """

    @abstractmethod
    def seed_base_data(self, conn: sqlite3.Connection) -> None:
        """Insert representative seed rows into *conn*.

        Seed data should represent a realistic pre-divergence state.
        """

    @abstractmethod
    def get_policy_assignments(self) -> list[dict[str, str]]:
        """Return policy assignments for this workload's columns.

        Returns
        -------
        list[dict]
            Each dict: ``{table: str, column: str, policy: str}``.
        """

    @abstractmethod
    def get_ground_truth_conflicts(self) -> list[dict[str, Any]]:
        """Return expected conflict scenarios for benchmarking.

        Returns
        -------
        list[dict]
            Each dict::

                {
                  "table": str,
                  "row_id": int,
                  "column": str,
                  "base_value": Any,
                  "value_a": Any,       # value in replica A
                  "value_b": Any,       # value in replica B
                  "expected_semantic_result": Any,
                  "expected_baseline_result": str,  # description of LWW winner
                }
        """

    # ------------------------------------------------------------------
    # Template method: setup()
    # ------------------------------------------------------------------

    def setup(self) -> dict[str, Any]:
        """Create base DB, seed data, replicate to three device databases,
        and inject controlled divergent changes from ground-truth conflicts.

        Returns
        -------
        dict
            ::

                {
                  "db_id": str,               # unique run identifier
                  "base_path": Path,
                  "replicas": {
                      "device_a": Path,
                      "device_b": Path,
                      "device_c": Path,
                  },
                }
        """
        db_id = str(uuid.uuid4())[:8]
        workload_dir = self.data_dir / self.name / db_id
        workload_dir.mkdir(parents=True, exist_ok=True)

        base_path = workload_dir / "base.db"

        # 1. Create and seed the base database
        with sqlite3.connect(str(base_path)) as conn:
            self.create_schema(conn)
            self.seed_base_data(conn)
            conn.commit()

        # 2. Copy to three replica databases
        replicas: dict[str, Path] = {}
        for device in ("device_a", "device_b", "device_c"):
            replica_path = workload_dir / f"{device}.db"
            shutil.copy2(str(base_path), str(replica_path))
            replicas[device] = replica_path

        # 3. Apply controlled divergent changes to device_a and device_b
        #    based on ground_truth_conflicts
        conflicts = self.get_ground_truth_conflicts()
        for conflict in conflicts:
            table = conflict["table"]
            row_id = conflict["row_id"]
            col = conflict["column"]
            val_a = conflict["value_a"]
            val_b = conflict["value_b"]

            # Apply value_a to device_a
            self._apply_value(replicas["device_a"], table, row_id, col, val_a)
            # Apply value_b to device_b
            self._apply_value(replicas["device_b"], table, row_id, col, val_b)
            # device_c stays at base (no divergence)

        return {
            "db_id": db_id,
            "base_path": base_path,
            "replicas": replicas,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_value(
        db_path: Path, table: str, row_id: int, column: str, value: Any
    ) -> None:
        """Write *value* to a specific cell using a parameterised UPDATE."""
        sql = f'UPDATE "{table}" SET "{column}" = ? WHERE id = ?;'  # noqa: S608
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(sql, (value, row_id))
            conn.commit()
