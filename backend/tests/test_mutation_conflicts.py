"""
backend/tests/test_mutation_conflicts.py
────────────────────────────────────────
Phase 2 Full Row-Mutation Conflict Test Suite (+ Adversarial Audit Extension).

Verifies:
 1.  INSERT vs INSERT primary-key collisions (divergent payloads flagged, payloads preserved).
 2.  INSERT vs INSERT identical duplicate delivery (idempotent clean convergence).
 3.  INSERT vs INSERT secondary UNIQUE constraint collisions (different PK, same unique column).
 4.  UPDATE vs DELETE concurrent mutations (flagged for review by default; evidence preserved).
 5.  UPDATE vs DELETE configurable tombstone policies (DELETE_WINS and UPDATE_RESURRECTS).
 6.  Clean single-sided delete is NOT flagged as a conflict.
 7.  DELETE vs DELETE idempotent convergence across 2 and 3 replicas.
 8.  Composite-PK tables reported in DetectResult.skipped_tables and SyncResult.skipped_tables,
     never silently skipped.
 9.  Durable tombstone propagation to unchanged stale replicas; mutated copies remain conflicts.
10.  Repeated synchronization after resolution.
11.  Conflict persistence, recovery, and transactional audit trails.
12.  Causality is recorded in conflict timestamps (informational), even though the
     state-based detector always flags UPDATE vs DELETE (limitation documented).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path
import pytest

from backend.engine.conflict_detector import ConflictDetector, ConflictInfo, DetectResult
from backend.engine.crdt_sync import CRDTSyncEngine, HLC
from backend.engine.merge_manager import MergeManager
from backend.engine.semantic_resolver import SemanticResolver, ResolutionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_workspace(tmp_path: Path):
    """
    Creates a temporary base database and working directory for replicas.
    Schema includes PK and a secondary UNIQUE column::

        items (
            id       INTEGER PRIMARY KEY,
            code     TEXT UNIQUE NOT NULL,
            name     TEXT,
            quantity INTEGER
        )
    """
    base_path = tmp_path / "base.db"
    with sqlite3.connect(base_path) as conn:
        conn.execute(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT,
                quantity INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO items (id, code, name, quantity) VALUES (1, 'C-01', 'Item One', 100)"
        )
        conn.execute(
            "INSERT INTO items (id, code, name, quantity) VALUES (2, 'C-02', 'Item Two', 200)"
        )
        conn.commit()

    engine = CRDTSyncEngine(base_db_path=str(base_path), data_dir=str(tmp_path))
    return {
        "base_path": str(base_path),
        "tmp_path": tmp_path,
        "engine": engine,
    }


def _detect(rep_a, rep_b, base_path, id_a="rep_a", id_b="rep_b") -> list[ConflictInfo]:
    """Helper: call detect() and return only the conflicts list (unwrapping DetectResult)."""
    result: DetectResult = ConflictDetector().detect(rep_a, rep_b, base_path, id_a, id_b)
    return result.conflicts


# ===========================================================================
# 1. INSERT vs INSERT Tests
# ===========================================================================

class TestInsertVsInsert:
    """Verifies PK collisions, UNIQUE constraint violations, and duplicate idempotency."""

    def test_insert_pk_collision_divergent_payloads_flagged(self, temp_workspace):
        """
        When Replica A and B independently insert the same PK with different payloads:
        Must be flagged for review, not silently overwritten. Payloads preserved.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        # Both insert row id=3 with different codes and names
        engine.apply_insert(rep_a, "rep_a", "items", {"id": 3, "code": "C-03-A", "name": "Inserted by A", "quantity": 10})
        engine.apply_insert(rep_b, "rep_b", "items", {"id": 3, "code": "C-03-B", "name": "Inserted by B", "quantity": 20})

        conflicts = _detect(rep_a, rep_b, base_path)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.conflict_type == "INSERT_INSERT"
        assert c.table == "items"
        assert c.row_id == 3
        assert c.status == "flagged"
        assert c.replica_a_value["code"] == "C-03-A"
        assert c.replica_b_value["code"] == "C-03-B"
        assert c.base_value is None

    def test_insert_identical_payloads_idempotent_no_conflict(self, temp_workspace):
        """
        When Replica A and B insert identical rows (duplicate delivery):
        Treated as idempotent duplicate — no conflict emitted.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        identical_payload = {"id": 4, "code": "C-04", "name": "Identical Item", "quantity": 50}
        engine.apply_insert(rep_a, "rep_a", "items", identical_payload)
        engine.apply_insert(rep_b, "rep_b", "items", identical_payload)

        conflicts = _detect(rep_a, rep_b, base_path)
        assert len(conflicts) == 0

    def test_insert_unique_index_collision_flagged(self, temp_workspace):
        """
        When Replica A and B insert different PKs, but identical value in a UNIQUE column:
        Must be flagged as UNIQUE_COLLISION to avoid SQLite constraint violation on merge.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        # Distinct PKs (10 vs 20), but identical UNIQUE code 'C-DUPLICATE'
        engine.apply_insert(rep_a, "rep_a", "items", {"id": 10, "code": "C-DUPLICATE", "name": "A Item", "quantity": 1})
        engine.apply_insert(rep_b, "rep_b", "items", {"id": 20, "code": "C-DUPLICATE", "name": "B Item", "quantity": 2})

        conflicts = _detect(rep_a, rep_b, base_path)

        unique_conflicts = [c for c in conflicts if c.conflict_type == "UNIQUE_COLLISION"]
        assert len(unique_conflicts) == 1
        c = unique_conflicts[0]
        assert c.column == "code"
        assert c.status == "flagged"
        assert c.replica_a_value["id"] == 10
        assert c.replica_b_value["id"] == 20


# ===========================================================================
# 2. UPDATE vs DELETE & Tombstone Tests
# ===========================================================================

class TestUpdateVsDelete:
    """Verifies concurrent UPDATE vs DELETE, tombstone policies, and causal ordering."""

    def test_concurrent_update_vs_delete_flagged_by_default(self, temp_workspace):
        """
        When Replica A modifies row 1 and Replica B deletes row 1:
        Must be flagged for review by default. Neither silently resurrected nor discarded.

        Note: The state-based detector always flags UPDATE+DELETE as a conflict
        regardless of timestamp ordering; causal ordering is informational only.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        engine.apply_change(rep_a, "rep_a", "items", 1, "name", "Item One Mutated")
        engine.apply_delete(rep_b, "rep_b", "items", 1)

        conflicts = _detect(rep_a, rep_b, base_path)

        upd_del_conflicts = [c for c in conflicts if c.conflict_type == "UPDATE_DELETE"]
        assert len(upd_del_conflicts) == 1
        c = upd_del_conflicts[0]
        assert c.row_id == 1
        assert c.status == "flagged"
        assert c.replica_a_value["name"] == "Item One Mutated"
        assert c.replica_b_value is None
        assert c.base_value["name"] == "Item One"

    def test_update_vs_delete_tombstone_policy_delete_wins(self, temp_workspace):
        """
        When tombstone_policy is configured as DELETE_WINS:
        Row is deleted on both replicas, update preserved in conflict audit log.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        engine.apply_change(rep_a, "rep_a", "items", 1, "name", "Item One Mutated")
        engine.apply_delete(rep_b, "rep_b", "items", 1)

        policies = {"items": {"__tombstone__": "DELETE_WINS"}}
        result = engine.sync_replicas(rep_a, rep_b, base_path, "rep_a", "rep_b", policies)

        assert result.auto_resolved >= 1
        # Verify row 1 is absent from both replicas
        with sqlite3.connect(rep_a) as conn:
            assert conn.execute("SELECT 1 FROM items WHERE id = 1").fetchone() is None
        with sqlite3.connect(rep_b) as conn:
            assert conn.execute("SELECT 1 FROM items WHERE id = 1").fetchone() is None

    def test_update_vs_delete_tombstone_policy_update_resurrects(self, temp_workspace):
        """
        When tombstone_policy is configured as UPDATE_RESURRECTS:
        The mutated row is retained on both replicas.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        engine.apply_change(rep_a, "rep_a", "items", 1, "name", "Resurrected Item")
        engine.apply_delete(rep_b, "rep_b", "items", 1)

        policies = {"items": {"__tombstone__": "UPDATE_RESURRECTS"}}
        result = engine.sync_replicas(rep_a, rep_b, base_path, "rep_a", "rep_b", policies)

        assert result.auto_resolved >= 1
        with sqlite3.connect(rep_a) as conn:
            row = conn.execute("SELECT name FROM items WHERE id = 1").fetchone()
            assert row is not None
            assert row[0] == "Resurrected Item"
        with sqlite3.connect(rep_b) as conn:
            row = conn.execute("SELECT name FROM items WHERE id = 1").fetchone()
            assert row is not None
            assert row[0] == "Resurrected Item"


# ===========================================================================
# 3. DELETE vs DELETE Tests
# ===========================================================================

class TestDeleteVsDelete:
    """Verifies idempotent deletion convergence across 2 and 3 replicas."""

    def test_delete_delete_convergence_two_replicas(self, temp_workspace):
        """
        When both replicas delete row 2:
        Idempotent convergence with no conflict emitted.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        engine.apply_delete(rep_a, "rep_a", "items", 2)
        engine.apply_delete(rep_b, "rep_b", "items", 2)

        conflicts = _detect(rep_a, rep_b, base_path)

        # Deleting the same row concurrently is an idempotent agreement
        del_conflicts = [c for c in conflicts if c.row_id == 2]
        assert len(del_conflicts) == 0

    def test_delete_delete_three_replicas_convergence(self, temp_workspace):
        """
        Three replicas A, B, C:
        A and B delete row 1. C deletes row 1 later.
        Repeated pairwise sync converges without recreating the row.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")
        rep_c = engine.create_replica("rep_c")

        engine.apply_delete(rep_a, "rep_a", "items", 1)
        engine.apply_delete(rep_b, "rep_b", "items", 1)
        engine.apply_delete(rep_c, "rep_c", "items", 1)

        policies = {"items": {}}
        engine.sync_replicas(rep_a, rep_b, base_path, "rep_a", "rep_b", policies)
        engine.sync_replicas(rep_b, rep_c, base_path, "rep_b", "rep_c", policies)
        engine.sync_replicas(rep_a, rep_c, base_path, "rep_a", "rep_c", policies)

        for p in (rep_a, rep_b, rep_c):
            with sqlite3.connect(p) as conn:
                assert conn.execute("SELECT 1 FROM items WHERE id = 1").fetchone() is None


# ===========================================================================
# 4. Delivery & Repetition Idempotency
# ===========================================================================

class TestDeliveryIdempotencyAndRecovery:
    """Verifies reordered, duplicate delivery, and repeated sync after resolution."""

    def test_repeated_sync_after_resolution_does_not_duplicate(self, temp_workspace):
        """
        Running sync a second time after conflict resolution does not re-apply or duplicate.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        # Create standard UPDATE conflict on quantity (SUM policy)
        engine.apply_change(rep_a, "rep_a", "items", 1, "quantity", 110)
        engine.apply_change(rep_b, "rep_b", "items", 1, "quantity", 120)

        policies = {"items": {"quantity": "SUM"}}
        res1 = engine.sync_replicas(rep_a, rep_b, base_path, "rep_a", "rep_b", policies)
        assert res1.auto_resolved == 1

        # Second sync
        res2 = engine.sync_replicas(rep_a, rep_b, base_path, "rep_a", "rep_b", policies)
        assert res2.total_conflicts == 0
        assert res2.auto_resolved == 0

        # State remains converged at 130
        with sqlite3.connect(rep_a) as conn:
            assert conn.execute("SELECT quantity FROM items WHERE id = 1").fetchone()[0] == 130
        with sqlite3.connect(rep_b) as conn:
            assert conn.execute("SELECT quantity FROM items WHERE id = 1").fetchone()[0] == 130

    def test_conflict_persistence_and_recovery_audit(self, temp_workspace):
        """
        Flagged conflicts are persisted in MergeManager with full evidence and can be retrieved.
        """
        manager = MergeManager(storage_path=str(temp_workspace["tmp_path"] / "conflicts.json"))
        c = ConflictInfo(
            conflict_id="audit-test-uuid",
            table="items",
            row_id=99,
            column="*",
            conflict_type="INSERT_INSERT",
            base_value=None,
            replica_a_value={"id": 99, "name": "Alpha"},
            replica_b_value={"id": 99, "name": "Beta"},
            replica_a_id="node_a",
            replica_b_id="node_b",
            replica_a_ts=100.0,
            replica_b_ts=200.0,
            detected_at="2026-10-11T12:00:00Z",
            status="flagged",
            explanation="INSERT collision test",
        )
        cid = manager.add_conflict(c)
        saved = manager.get_conflict(cid)

        assert saved is not None
        assert saved["conflict_type"] == "INSERT_INSERT"
        assert saved["value_a"]["name"] == "Alpha"
        assert saved["value_b"]["name"] == "Beta"
        assert saved["status"] == "flagged"

    def test_all_flagged_row_mutation_conflicts_recover_after_manager_restart(self, temp_workspace):
        """Persist/reload full evidence for PK, UNIQUE, and UPDATE-vs-DELETE conflicts."""
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]
        rep_a = engine.create_replica("persist_a")
        rep_b = engine.create_replica("persist_b")

        engine.apply_insert(rep_a, "persist_a", "items", {"id": 3, "code": "PK-A", "name": "A", "quantity": 1})
        engine.apply_insert(rep_b, "persist_b", "items", {"id": 3, "code": "PK-B", "name": "B", "quantity": 2})
        engine.apply_insert(rep_a, "persist_a", "items", {"id": 10, "code": "UNIQUE-X", "name": "A unique", "quantity": 3})
        engine.apply_insert(rep_b, "persist_b", "items", {"id": 20, "code": "UNIQUE-X", "name": "B unique", "quantity": 4})
        engine.apply_change(rep_a, "persist_a", "items", 1, "name", "updated")
        engine.apply_delete(rep_b, "persist_b", "items", 1)
        engine.apply_delete(rep_a, "persist_a", "items", 2)
        engine.apply_delete(rep_b, "persist_b", "items", 2)

        conflicts = _detect(rep_a, rep_b, base_path, "persist_a", "persist_b")
        by_type = {conflict.conflict_type: conflict for conflict in conflicts}
        assert set(by_type) == {"INSERT_INSERT", "UNIQUE_COLLISION", "UPDATE_DELETE"}
        assert not any(conflict.row_id == 2 for conflict in conflicts)  # DELETE/DELETE is agreement.

        store = temp_workspace["tmp_path"] / "row_mutation_conflicts.json"
        writer = MergeManager(storage_path=str(store))
        for conflict in conflicts:
            writer.add_conflict(conflict)
        recovered = MergeManager(storage_path=str(store))

        for conflict_type, original in by_type.items():
            saved = recovered.get_conflict(original.conflict_id)
            assert saved is not None
            assert saved["conflict_type"] == conflict_type
            assert saved["base_value"] == original.base_value
            assert saved["value_a"] == original.replica_a_value
            assert saved["value_b"] == original.replica_b_value
            assert saved["status"] == "flagged"


# ===========================================================================
# 5. Adversarial Audit — Causality Documentation Tests  [NEW]
# ===========================================================================

class TestCausalityDocumented:
    """
    Documents the causality limitation of the state-based detector.

    The detector uses snapshot diffing, not vector clocks.  It cannot
    automatically determine whether a DELETE causally dominates an UPDATE.
    All UPDATE+state-absent scenarios are flagged conservatively.

    These tests verify:
    (a) Timestamps ARE recorded in conflict records for reviewer context.
    (b) A clean single-sided delete (no mutation on the other replica) is
        NOT flagged.
    (c) Both causally-ordered and concurrent UPDATE+DELETE are flagged the
        same way — distinguishing them requires reviewer inspection of the
        recorded timestamps.
    """

    def test_single_sided_delete_not_flagged(self, temp_workspace):
        """
        A deleted B, A did not mutate → clean delete, no conflict.
        This is the invariant that prevents phantom conflicts on every deletion.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a_clean")
        rep_b = engine.create_replica("rep_b_clean")

        # B deletes row 1; A never touches it
        engine.apply_delete(rep_b, "rep_b_clean", "items", 1)

        conflicts = _detect(rep_a, rep_b, base_path, "rep_a_clean", "rep_b_clean")
        upd_del = [c for c in conflicts if c.conflict_type == "UPDATE_DELETE" and c.row_id == 1]
        assert len(upd_del) == 0, (
            f"Expected no conflict for clean single-sided delete, "
            f"got: {[c.explanation for c in upd_del]}"
        )

    def test_update_then_delete_still_flagged_with_timestamps_recorded(self, temp_workspace):
        """
        A updates row 1.  B deletes row 1 (regardless of order or causal intent).
        The state-based detector flags the conflict; timestamps are recorded for
        reviewer inspection.

        This test documents the current limitation: causal ordering is NOT
        auto-detected.  The conflict record carries both timestamps so a human
        or policy engine can inspect them.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a_ts")
        rep_b = engine.create_replica("rep_b_ts")

        engine.apply_change(rep_a, "rep_a_ts", "items", 1, "name", "Updated")
        engine.apply_delete(rep_b, "rep_b_ts", "items", 1)

        conflicts = _detect(rep_a, rep_b, base_path, "rep_a_ts", "rep_b_ts")
        upd_del = [c for c in conflicts if c.conflict_type == "UPDATE_DELETE" and c.row_id == 1]

        assert len(upd_del) == 1
        c = upd_del[0]
        assert c.status == "flagged"
        # Timestamps must be populated (not 0 or None)
        assert c.replica_a_ts > 0, "UPDATE timestamp should be recorded"
        assert c.replica_b_ts > 0, "DELETE timestamp should be recorded"

    def test_conflict_explanation_contains_op_context(self, temp_workspace):
        """
        The conflict explanation string should contain context about the last
        known op type on the deleting replica (e.g., 'DELETE' or 'unknown').
        This helps reviewers understand the nature of the conflict.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a_ctx")
        rep_b = engine.create_replica("rep_b_ctx")

        engine.apply_change(rep_a, "rep_a_ctx", "items", 1, "name", "Updated")
        engine.apply_delete(rep_b, "rep_b_ctx", "items", 1)

        conflicts = _detect(rep_a, rep_b, base_path, "rep_a_ctx", "rep_b_ctx")
        upd_del = [c for c in conflicts if c.conflict_type == "UPDATE_DELETE" and c.row_id == 1]
        assert len(upd_del) == 1
        # Explanation should mention the op type context
        explanation = upd_del[0].explanation or ""
        assert "DELETE" in explanation or "modified" in explanation.lower(), (
            f"Expected explanation to contain op context, got: {explanation!r}"
        )


# ===========================================================================
# 6. Adversarial Audit — Composite-PK Surfacing Tests  [NEW]
# ===========================================================================

class TestCompositePKSurfaced:
    """
    Verifies that tables with composite primary keys are reported in
    DetectResult.skipped_tables rather than silently ignored.

    Root cause fixed: ``_get_pk_column`` previously used ``pk == 1``
    (which matched only the first column of a composite PK), making
    composite-PK tables appear single-PK.  Fixed to use ``pk > 0``
    and collect ALL PK-participating columns; returns None when count != 1.
    """

    def test_composite_pk_table_is_in_skipped_tables(self, tmp_path: Path):
        """
        A table with a two-column composite PK cannot be addressed by a single
        row_id scalar.  detect() must include it in skipped_tables.
        """
        base_path = tmp_path / "base.db"
        with sqlite3.connect(base_path) as conn:
            conn.execute(
                """
                CREATE TABLE composite_pk_table (
                    col_a INTEGER,
                    col_b INTEGER,
                    value TEXT,
                    PRIMARY KEY (col_a, col_b)
                )
                """
            )
            conn.execute("INSERT INTO composite_pk_table VALUES (1, 2, 'hello')")
            conn.commit()

        rep_a = str(tmp_path / "rep_a.db")
        rep_b = str(tmp_path / "rep_b.db")
        shutil.copy2(base_path, rep_a)
        shutil.copy2(base_path, rep_b)

        result: DetectResult = ConflictDetector().detect(
            rep_a, rep_b, str(base_path), "ra", "rb"
        )
        assert "composite_pk_table" in result.skipped_tables, (
            f"Expected 'composite_pk_table' in skipped_tables, got: {result.skipped_tables}"
        )
        # No conflicts should be emitted for the skipped table
        comp_conflicts = [c for c in result.conflicts if c.table == "composite_pk_table"]
        assert len(comp_conflicts) == 0

    def test_single_pk_table_not_in_skipped_tables(self, tmp_path: Path):
        """
        A normal single-column PK table must NOT appear in skipped_tables.
        Regression guard: ensure the fix did not over-exclude single-PK tables.
        """
        base_path = tmp_path / "base.db"
        with sqlite3.connect(base_path) as conn:
            conn.execute("CREATE TABLE normal (id INTEGER PRIMARY KEY, val TEXT)")
            conn.commit()

        rep_a = str(tmp_path / "rep_a.db")
        rep_b = str(tmp_path / "rep_b.db")
        shutil.copy2(base_path, rep_a)
        shutil.copy2(base_path, rep_b)

        result: DetectResult = ConflictDetector().detect(
            rep_a, rep_b, str(base_path), "ra", "rb"
        )
        assert "normal" not in result.skipped_tables, (
            f"Single-PK table 'normal' should not be in skipped_tables"
        )

    def test_composite_pk_reported_in_sync_result(self, tmp_path: Path):
        """
        When sync_replicas processes a DB containing a composite-PK table,
        the skipped table must appear in SyncResult.skipped_tables.
        """
        base_path = tmp_path / "base.db"
        with sqlite3.connect(base_path) as conn:
            conn.execute(
                """
                CREATE TABLE multi_pk (
                    a INTEGER,
                    b INTEGER,
                    val TEXT,
                    PRIMARY KEY (a, b)
                )
                """
            )
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_path), data_dir=str(tmp_path))
        rep_a = engine.create_replica("rpa")
        rep_b = engine.create_replica("rpb")

        result = engine.sync_replicas(rep_a, rep_b, str(base_path), "rpa", "rpb", {})
        assert "multi_pk" in result.skipped_tables, (
            f"Expected 'multi_pk' in SyncResult.skipped_tables, got: {result.skipped_tables}"
        )


# ===========================================================================
# 7. Adversarial Audit — Stale Replica Tombstone Gap  [NEW]
# ===========================================================================

class TestStaleTombstonePropagation:
    """
    Durable tombstones propagate to unchanged replicas, while local mutations
    are preserved for conflict review.
    """

    def test_stale_replica_mutated_row_vs_tombstone_is_flagged(self, temp_workspace):
        """
        Scenario:
          - A deletes row 1.
          - C modifies row 1 (concurrent with A's delete).
          - sync(B, C) with base: C's mutation conflicts with A's deletion,
            which is visible in base state (row 1 still in base).

        Expected: detect(A_state, C) → UPDATE_DELETE conflict flagged.
        (We compare A's state directly with C to demonstrate the conflict.)
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a_stale")
        rep_c = engine.create_replica("rep_c_stale")

        # A deletes row 1
        engine.apply_delete(rep_a, "rep_a_stale", "items", 1)

        # C modifies row 1 (concurrent — neither knows about the other)
        engine.apply_change(rep_c, "rep_c_stale", "items", 1, "name", "C Modified")

        # Directly detect between A (deleted) and C (mutated) against base
        conflicts = _detect(rep_a, rep_c, base_path, "rep_a_stale", "rep_c_stale")

        upd_del = [c for c in conflicts if c.conflict_type == "UPDATE_DELETE" and c.row_id == 1]
        assert len(upd_del) == 1, (
            f"Expected 1 UPDATE_DELETE conflict between A (deleted) and C (mutated), "
            f"got {len(upd_del)}: {[c.explanation for c in upd_del]}"
        )
        assert upd_del[0].status == "flagged"
        # A deleted (replica_a_value = None), C modified (replica_b_value = dict)
        assert upd_del[0].replica_a_value is None   # A deleted
        assert upd_del[0].replica_b_value is not None  # C has modified row

    def test_stale_unmodified_replica_clean_delete_no_conflict(self, temp_workspace):
        """
        Scenario:
          - A deletes row 1.
          - C never touched row 1 (still has base-equal value).
          - detect(A, C, base): C has the row, A does not. C's value equals base.

        Expected: sync propagates the tombstone and persists it on C.
        """
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]

        rep_a = engine.create_replica("rep_a_stale2")
        rep_c = engine.create_replica("rep_c_stale2")

        # A deletes row 1; C never touches it
        engine.apply_delete(rep_a, "rep_a_stale2", "items", 1)

        first = engine.sync_replicas(rep_a, rep_c, base_path, "rep_a_stale2", "rep_c_stale2", {})
        with sqlite3.connect(rep_c) as conn:
            assert conn.execute("SELECT 1 FROM items WHERE id = 1").fetchone() is None
            first_count = conn.execute(
                "SELECT COUNT(*) FROM _ss_change_log WHERE replica_id = ? AND op_type = 'DELETE'",
                ("rep_c_stale2",),
            ).fetchone()[0]
        assert any(c["policy"] == "DELETE_DELIVERY" for c in first.applied_changes)
        assert first_count == 1

        # Duplicate delivery is idempotent and does not append another tombstone.
        second = engine.sync_replicas(rep_a, rep_c, base_path, "rep_a_stale2", "rep_c_stale2", {})
        with sqlite3.connect(rep_c) as conn:
            second_count = conn.execute(
                "SELECT COUNT(*) FROM _ss_change_log WHERE replica_id = ? AND op_type = 'DELETE'",
                ("rep_c_stale2",),
            ).fetchone()[0]
        assert second_count == first_count
        assert not any(c["policy"] == "TOMBSTONE_DELIVERY" for c in second.applied_changes)

    def test_delayed_tombstone_does_not_overwrite_local_mutation(self, temp_workspace):
        engine: CRDTSyncEngine = temp_workspace["engine"]
        base_path = temp_workspace["base_path"]
        rep_a = engine.create_replica("rep_a_delayed")
        rep_c = engine.create_replica("rep_c_delayed")

        engine.apply_delete(rep_a, "rep_a_delayed", "items", 1)
        # C changes locally before the old tombstone is delivered.
        engine.apply_change(rep_c, "rep_c_delayed", "items", 1, "name", "Local update")
        result = engine.sync_replicas(
            rep_a, rep_c, base_path, "rep_a_delayed", "rep_c_delayed", {}
        )
        with sqlite3.connect(rep_c) as conn:
            assert conn.execute("SELECT name FROM items WHERE id = 1").fetchone()[0] == "Local update"
        assert result.flagged_for_review == 1
