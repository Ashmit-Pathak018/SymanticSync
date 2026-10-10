"""
backend/engine/merge_manager.py
─────────────────────────────────
Coordinates conflict persistence, manual review tracking, and resolution.
Stores conflicts in-memory and persists to data/conflicts.json.
Can operate standalone or bind to AppState.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class MergeManager:
    """
    Manages conflict recording and resolution.
    """

    def __init__(
        self,
        app_state: Any = None,
        storage_path: str = "data/conflicts.json",
    ) -> None:
        self._state = app_state
        self._storage_path = Path(storage_path)
        self._conflicts: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    self._conflicts = json.load(f)
            except Exception:
                self._conflicts = {}

    def _save(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._conflicts, f, indent=2, default=str)
        except Exception:
            pass

    def add_conflict(self, conflict: Any) -> str:
        """
        Store a detected conflict. Accepts ConflictInfo dataclass or dict.
        """
        if hasattr(conflict, "conflict_id"):
            cid = conflict.conflict_id
            rec = {
                "conflict_id": cid,
                "table": conflict.table,
                "row_id": conflict.row_id,
                "column": conflict.column,
                "base_value": conflict.base_value,
                "value_a": conflict.replica_a_value,
                "value_b": conflict.replica_b_value,
                "replica_a_id": conflict.replica_a_id,
                "replica_b_id": conflict.replica_b_id,
                "replica_a_ts": conflict.replica_a_ts,
                "replica_b_ts": conflict.replica_b_ts,
                "status": "pending",
                "detected_at": getattr(
                    conflict, "detected_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                ),
            }
        else:
            cid = conflict.get("conflict_id", str(time.time()))
            rec = dict(conflict)
            if "status" not in rec:
                rec["status"] = "pending"

        self._conflicts[cid] = rec
        if self._state and hasattr(self._state, "store_conflict"):
            self._state.store_conflict(cid, rec)
        self._save()
        return cid

    def store_conflicts(self, conflicts: list[Any]) -> None:
        for c in conflicts:
            self.add_conflict(c)

    def apply_resolution(
        self,
        conflict_id: str,
        resolution: Any,
        manual_value: Any = None,
    ) -> dict[str, Any]:
        """
        Mark conflict as resolved or flagged based on ResolutionResult.
        """
        rec = self._conflicts.get(conflict_id, {})
        status = getattr(resolution, "status", "resolved")
        res_val = manual_value if manual_value is not None else getattr(resolution, "resolved_value", resolution)
        explanation = getattr(resolution, "explanation", "")

        rec["status"] = status
        rec["resolved_value"] = res_val
        rec["explanation"] = explanation
        rec["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self._conflicts[conflict_id] = rec
        if self._state and hasattr(self._state, "store_conflict"):
            self._state.store_conflict(conflict_id, rec)
        self._save()
        return rec

    def list_conflicts(self, status: str = "all") -> list[dict[str, Any]]:
        self._load()
        if status == "all":
            return list(self._conflicts.values())
        return [c for c in self._conflicts.values() if c.get("status") == status]

    def get_conflict(self, conflict_id: str) -> dict[str, Any] | None:
        self._load()
        return self._conflicts.get(conflict_id)

    def clear_all(self) -> None:
        self._conflicts.clear()
        if self._storage_path.exists():
            try:
                self._storage_path.unlink()
            except Exception:
                pass
