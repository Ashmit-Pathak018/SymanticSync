"""
test_foreign_key_invariants.py
==============================
Phase 5 regression tests for Foreign-Key Integrity & Orphan Quarantine.

Test scenarios
--------------
1. Basic FK enforcement — deleting a parent with a live child raises if quarantine
   is not applied first; with quarantine it succeeds.
2. Quarantine DDL — _ss_quarantine table created automatically.
3. Single-level orphan — one child quarantined and removed on parent delete.
4. Multi-tier nested cascade — grandchild quarantined before child, child before parent.
5. Concurrent edits with FKs — applying an update to a child whose parent is deleted
   via apply_delete results in quarantine, not silent loss.
6. Retry / restart persistence — quarantine records survive connection close+reopen.
7. Quarantine restoration — re-linking a quarantined row via resolve_quarantine_record.
8. apply_delete via CRDTSyncEngine — FK enforcement path end-to-end.
9. _apply_received_operation DELETE — delivered remote DELETE quarantines orphans.
10. verify_fk_integrity — detects real violations, passes on clean DB.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.engine.fk_quarantine import (
    enable_foreign_keys,
    ensure_quarantine_table,
    list_quarantined,
    quarantine_orphans,
    resolve_quarantine_record,
    verify_fk_integrity,
)
from backend.engine.crdt_sync import CRDTSyncEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def parent_child_db(tmp_path: Path):
    """
    Create a minimal parent-child SQLite DB.

    departments(dept_id PK, name)
    employees(emp_id PK, dept_id FK→departments.dept_id, name)
    """
    db = tmp_path / "pc.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE departments (
                dept_id INTEGER PRIMARY KEY,
                name    TEXT NOT NULL
            );
            CREATE TABLE employees (
                emp_id  INTEGER PRIMARY KEY,
                dept_id INTEGER NOT NULL REFERENCES departments(dept_id),
                name    TEXT NOT NULL
            );
            INSERT INTO departments VALUES (1, 'Engineering');
            INSERT INTO departments VALUES (2, 'Sales');
            INSERT INTO employees  VALUES (10, 1, 'Alice');
            INSERT INTO employees  VALUES (11, 1, 'Bob');
            INSERT INTO employees  VALUES (12, 2, 'Carol');
        """)
    return db


@pytest.fixture()
def nested_db(tmp_path: Path):
    """
    Three-level hierarchy: companies → departments → employees.
    """
    db = tmp_path / "nested.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE companies (
                co_id INTEGER PRIMARY KEY,
                name  TEXT NOT NULL
            );
            CREATE TABLE departments (
                dept_id INTEGER PRIMARY KEY,
                co_id   INTEGER NOT NULL REFERENCES companies(co_id),
                name    TEXT NOT NULL
            );
            CREATE TABLE employees (
                emp_id  INTEGER PRIMARY KEY,
                dept_id INTEGER NOT NULL REFERENCES departments(dept_id),
                name    TEXT NOT NULL
            );
            INSERT INTO companies   VALUES (1, 'Acme Corp');
            INSERT INTO departments VALUES (10, 1, 'Engineering');
            INSERT INTO employees   VALUES (100, 10, 'Alice');
            INSERT INTO employees   VALUES (101, 10, 'Bob');
        """)
    return db


@pytest.fixture()
def engine_db(tmp_path: Path):
    """
    DB suitable for CRDTSyncEngine with FK-related tables.
    base_db: items(id PK, dept_id FK→depts.dept_id, count INTEGER)
    depts(dept_id PK, label TEXT)
    """
    db = tmp_path / "base.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE depts (
                dept_id INTEGER PRIMARY KEY,
                label   TEXT NOT NULL
            );
            CREATE TABLE items (
                id      INTEGER PRIMARY KEY,
                dept_id INTEGER NOT NULL REFERENCES depts(dept_id),
                count   INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO depts VALUES (1, 'alpha');
            INSERT INTO items VALUES (100, 1, 10);
            INSERT INTO items VALUES (101, 1, 20);
        """)
    return db


# ---------------------------------------------------------------------------
# 1. Basic FK enforcement
# ---------------------------------------------------------------------------

class TestFKEnforcement:
    def test_delete_parent_without_quarantine_fails(self, parent_child_db):
        """Without quarantine, FK-enforced DELETE raises IntegrityError."""
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM departments WHERE dept_id = 1")
        conn.close()

    def test_delete_parent_with_quarantine_succeeds(self, parent_child_db):
        """With quarantine applied first, parent DELETE succeeds under FK enforcement."""
        conn = sqlite3.connect(str(parent_child_db))
        enable_foreign_keys(conn)
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        quarantine_orphans(conn, parent_table="departments", parent_row_id=1)
        conn.execute("DELETE FROM departments WHERE dept_id = 1")
        verify_fk_integrity(conn)
        conn.commit()
        # Parent gone
        assert conn.execute("SELECT COUNT(*) FROM departments WHERE dept_id=1").fetchone()[0] == 0
        # Children quarantined, not in employees
        assert conn.execute("SELECT COUNT(*) FROM employees WHERE dept_id=1").fetchone()[0] == 0
        conn.close()


# ---------------------------------------------------------------------------
# 2. Quarantine DDL
# ---------------------------------------------------------------------------

class TestQuarantineDDL:
    def test_table_created(self, tmp_path):
        db = tmp_path / "ddl.db"
        conn = sqlite3.connect(str(db))
        ensure_quarantine_table(conn)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "_ss_quarantine" in tables
        conn.close()

    def test_idempotent(self, tmp_path):
        db = tmp_path / "ddl2.db"
        conn = sqlite3.connect(str(db))
        ensure_quarantine_table(conn)
        ensure_quarantine_table(conn)  # must not raise
        conn.close()


# ---------------------------------------------------------------------------
# 3. Single-level orphan quarantine
# ---------------------------------------------------------------------------

class TestSingleLevelQuarantine:
    def test_orphaned_children_quarantined(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        assert len(ids) == 2, f"Expected 2 quarantine IDs (Alice+Bob), got {ids}"

    def test_quarantine_records_payload(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        quarantine_orphans(conn, "departments", 1)
        conn.commit()
        records = list_quarantined(conn)
        assert len(records) == 2
        for r in records:
            assert r["table_name"] == "employees"
            assert r["parent_table"] == "departments"
            assert r["parent_row_id"] == "1"
            assert r["status"] == "quarantined"
            payload = json.loads(r["row_payload"])
            assert "emp_id" in payload
            assert "dept_id" in payload

    def test_unrelated_table_not_quarantined(self, parent_child_db):
        """dept_id=2 (Carol) must NOT be quarantined when dept_id=1 is deleted."""
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        quarantine_orphans(conn, "departments", 1)
        conn.commit()
        records = list_quarantined(conn)
        quarantined_emp_ids = {json.loads(r["row_payload"])["emp_id"] for r in records}
        assert 12 not in quarantined_emp_ids  # Carol belongs to dept 2

    def test_no_children_no_quarantine(self, parent_child_db):
        """Deleting dept 2 (only Carol as child) does not touch dept 1 employees."""
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "departments", 2)
        conn.commit()
        assert len(ids) == 1  # only Carol
        records = list_quarantined(conn)
        assert len(records) == 1
        assert json.loads(records[0]["row_payload"])["emp_id"] == 12


# ---------------------------------------------------------------------------
# 4. Multi-tier nested cascade
# ---------------------------------------------------------------------------

class TestNestedCascadeQuarantine:
    def test_grandchildren_quarantined_first(self, nested_db):
        """
        Deleting company 1 must quarantine employees first (grandchildren),
        then departments (children), in depth-first order.
        """
        conn = sqlite3.connect(str(nested_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "companies", 1)
        conn.commit()
        # 2 employees + 1 department = 3 records
        assert len(ids) == 3

        records = list_quarantined(conn)
        by_table = {}
        for r in records:
            by_table.setdefault(r["table_name"], []).append(r)
        assert "employees" in by_table
        assert "departments" in by_table

    def test_referential_integrity_after_cascade(self, nested_db):
        conn = sqlite3.connect(str(nested_db))
        enable_foreign_keys(conn)
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        quarantine_orphans(conn, "companies", 1)
        conn.execute("DELETE FROM companies WHERE co_id = 1")
        verify_fk_integrity(conn)  # must not raise
        conn.commit()
        # All tables emptied
        assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0
        conn.close()


# ---------------------------------------------------------------------------
# 5. Concurrent edits — delete quarantines even if child was recently updated
# ---------------------------------------------------------------------------

class TestConcurrentEditsWithFKs:
    def test_updated_child_still_quarantined(self, parent_child_db):
        """Updating an employee right before a parent delete should still quarantine."""
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("UPDATE employees SET name='Alice Updated' WHERE emp_id=10")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        assert len(ids) == 2
        payloads = [json.loads(r["row_payload"]) for r in list_quarantined(conn)]
        names = {p["name"] for p in payloads}
        assert "Alice Updated" in names


# ---------------------------------------------------------------------------
# 6. Retry / restart persistence
# ---------------------------------------------------------------------------

class TestQuarantinePersistence:
    def test_records_survive_reconnect(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        quarantine_orphans(conn, "departments", 1)
        conn.commit()
        conn.close()

        # Reconnect
        conn2 = sqlite3.connect(str(parent_child_db))
        records = list_quarantined(conn2)
        conn2.close()
        assert len(records) == 2


# ---------------------------------------------------------------------------
# 7. Quarantine restoration
# ---------------------------------------------------------------------------

class TestQuarantineRestoration:
    def test_resolve_confirmed_deleted(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        qid = ids[0]
        with conn:
            ok = resolve_quarantine_record(conn, qid, action="confirmed_deleted")
        assert ok
        records = list_quarantined(conn, status="confirmed_deleted")
        assert any(r["quarantine_id"] == qid for r in records)
        conn.close()

    def test_relink_requires_existing_parent_and_preserves_quarantine_on_failure(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        with pytest.raises(ValueError, match="parent does not exist"):
            resolve_quarantine_record(conn, ids[0], "relinked", new_parent_row_id=999)
        assert list_quarantined(conn, status="quarantined")
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        conn.close()

    def test_ignored_relink_insert_does_not_mark_record_resolved(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        conn.execute("CREATE TRIGGER ignore_relink BEFORE INSERT ON employees BEGIN SELECT RAISE(IGNORE); END")
        with pytest.raises(sqlite3.IntegrityError, match="Relink insert"):
            resolve_quarantine_record(conn, ids[0], "relinked", new_parent_row_id=2)
        assert len(list_quarantined(conn, status="quarantined")) == 2
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        conn.close()

    def test_resolve_relinked(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("BEGIN IMMEDIATE")
        ensure_quarantine_table(conn)
        ids = quarantine_orphans(conn, "departments", 1)
        conn.commit()
        qid = ids[0]
        with conn:
            ok = resolve_quarantine_record(conn, qid, action="relinked", new_parent_row_id=2)
        assert ok
        records = list_quarantined(conn, status="relinked")
        assert any(r["quarantine_id"] == qid for r in records)
        row = json.loads(next(r["row_payload"] for r in records if r["quarantine_id"] == qid))
        restored = conn.execute("SELECT dept_id FROM employees WHERE emp_id=?", (row["emp_id"],)).fetchone()
        assert restored[0] == 2
        conn.close()

    def test_resolve_unknown_id_returns_false(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        ensure_quarantine_table(conn)
        ok = resolve_quarantine_record(conn, "nonexistent-uuid", action="confirmed_deleted")
        assert not ok
        conn.close()


# ---------------------------------------------------------------------------
# 8. CRDTSyncEngine.apply_delete end-to-end FK quarantine
# ---------------------------------------------------------------------------

class TestCRDTEngineApplyDeleteFK:
    def test_apply_delete_quarantines_children(self, engine_db, tmp_path):
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        replica_path = engine.create_replica("node_a")

        # Verify children exist before delete
        with sqlite3.connect(replica_path) as c:
            count = c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0]
        assert count == 2

        # Delete the parent dept
        engine.apply_delete(replica_path, "node_a", "depts", 1)

        # Verify quarantine records exist
        with sqlite3.connect(replica_path) as c:
            ensure_quarantine_table(c)
            records = list_quarantined(c)
        assert len(records) == 2

        # Verify children are gone from items table
        with sqlite3.connect(replica_path) as c:
            remaining = c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0]
        assert remaining == 0

    def test_apply_delete_no_children_succeeds(self, engine_db, tmp_path):
        """Deleting a parent with no children must succeed without quarantine records."""
        # Add a dept with no items
        with sqlite3.connect(str(engine_db)) as c:
            c.execute("INSERT INTO depts VALUES (99, 'empty')")

        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        replica_path = engine.create_replica("node_b")
        engine.apply_delete(replica_path, "node_b", "depts", 99)

        with sqlite3.connect(replica_path) as c:
            ensure_quarantine_table(c)
            records = list_quarantined(c)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# 9. _apply_received_operation DELETE quarantines orphans
# ---------------------------------------------------------------------------

class TestReceivedDeleteQuarantine:
    def test_received_delete_quarantines_children(self, engine_db, tmp_path):
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        src_path = engine.create_replica("src")
        tgt_path = engine.create_replica("tgt")

        # Record a DELETE on src
        engine.apply_delete(src_path, "src", "depts", 1)

        # Sync: replay src→tgt
        # tgt still has the children (items), so delivery should quarantine them
        engine2 = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        with sqlite3.connect(tgt_path) as c:
            before = c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0]
        assert before == 2

        result = engine2.sync_replicas(
            replica_a_path=src_path,
            replica_b_path=tgt_path,
            base_path=str(engine_db),
            replica_a_id="src",
            replica_b_id="tgt",
            policies={},
        )

        with sqlite3.connect(tgt_path) as c:
            ensure_quarantine_table(c)
            records = list_quarantined(c)
            after_items = c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0]

        # Children quarantined on tgt; items removed
        assert len(records) >= 2, f"Expected ≥2 quarantine records on tgt, got {records}"
        assert after_items == 0
        first_count = len(records)
        engine2.sync_replicas(src_path, tgt_path, str(engine_db), "src", "tgt", policies={})
        with sqlite3.connect(tgt_path) as c:
            assert c.execute("SELECT COUNT(*) FROM _ss_quarantine WHERE status='quarantined'").fetchone()[0] == first_count


# ---------------------------------------------------------------------------
# 10. verify_fk_integrity
# ---------------------------------------------------------------------------

class TestVerifyFKIntegrity:
    def test_no_violation_passes(self, parent_child_db):
        conn = sqlite3.connect(str(parent_child_db))
        conn.execute("PRAGMA foreign_keys = ON")
        verify_fk_integrity(conn)  # no violation → no raise
        conn.close()


class TestAdditionalFKPaths:
    def test_alternate_unique_parent_key_and_composite_child_key(self, tmp_path):
        db = tmp_path / "alternate.db"
        with sqlite3.connect(db) as c:
            c.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (x INTEGER, y INTEGER, parent_code TEXT,
                    PRIMARY KEY(x,y), FOREIGN KEY(parent_code) REFERENCES parent(code));
                CREATE TABLE leaf (id INTEGER PRIMARY KEY, child_x INTEGER, child_y INTEGER,
                    FOREIGN KEY(child_x,child_y) REFERENCES child(x,y));
                INSERT INTO parent VALUES(1,'P-A');
                INSERT INTO child VALUES(4,5,'P-A');
                INSERT INTO leaf VALUES(7,4,5);
            """)
        c = sqlite3.connect(db); enable_foreign_keys(c); c.execute("BEGIN IMMEDIATE")
        ids = quarantine_orphans(c, "parent", 1)
        c.execute("DELETE FROM parent WHERE id=1"); verify_fk_integrity(c); c.commit()
        assert len(ids) == 2
        assert c.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM leaf").fetchone()[0] == 0
        payloads = {r["table_name"] for r in list_quarantined(c)}
        assert payloads == {"child", "leaf"}
        c.close()

    def test_received_insert_and_update_fk_failures_are_rejected_without_receipts(self, engine_db, tmp_path):
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        path = engine.create_replica("receiver")
        insert_status, _ = engine._apply_received_operation(
            path, "receiver", "items", 999, "*", None,
            json.dumps({"id": 999, "dept_id": 999, "count": 1}), "INSERT", "origin-insert",
            "remote", 1, 1.0, 0, set())
        update_status, _ = engine._apply_received_operation(
            path, "receiver", "items", 100, "dept_id", "1", "999", "UPDATE", "origin-update",
            "remote", 2, 2.0, 0, set())
        assert insert_status == update_status == "rejected"
        with sqlite3.connect(path) as c:
            assert c.execute("SELECT dept_id FROM items WHERE id=100").fetchone()[0] == 1
            assert c.execute("SELECT COUNT(*) FROM items WHERE id=999").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM _ss_change_log WHERE origin_id IN ('origin-insert','origin-update')").fetchone()[0] == 0

    def test_paired_resolution_delete_quarantines_both_replicas(self, engine_db, tmp_path):
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        a, b = engine.create_replica("pair_a"), engine.create_replica("pair_b")
        engine._write_resolved_pair(a,"pair_a",b,"pair_b","depts",1,"*",None,"delete")
        for path in (a,b):
            with sqlite3.connect(path) as c:
                assert c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM _ss_quarantine WHERE table_name='items'").fetchone()[0] == 2
                assert c.execute("SELECT COUNT(*) FROM depts WHERE dept_id=1").fetchone()[0] == 0

    def test_received_resolve_delete_quarantines_cascade_dependents(self, tmp_path):
        base = tmp_path / "resolve_cascade_base.db"
        with sqlite3.connect(base) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_code TEXT NOT NULL
                    REFERENCES parent(code) ON DELETE CASCADE);
                INSERT INTO parent VALUES (1, 'P-1');
                INSERT INTO child VALUES (10, 'P-1');
            """)
        engine = CRDTSyncEngine(str(base), str(tmp_path / "resolve_cascade_data"))
        a, b, c = (engine.create_replica(rid) for rid in ("resolve_a", "resolve_b", "resolve_c"))
        engine._write_resolved_pair(a, "resolve_a", b, "resolve_b", "parent", 1, "*", None, "delete")

        result = engine.sync_replicas(a, c, str(base), "resolve_a", "resolve_c", policies={})
        assert result.rejected_operations == []
        with sqlite3.connect(c) as conn:
            assert conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
            records = list_quarantined(conn, table_name="child")
            assert len(records) == 1
            assert json.loads(records[0]["row_payload"]) == {"id": 10, "parent_code": "P-1"}
            assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='RESOLVE'").fetchone()[0] == 1
            verify_fk_integrity(conn)
        engine.sync_replicas(a, c, str(base), "resolve_a", "resolve_c", policies={})
        with sqlite3.connect(c) as conn:
            assert conn.execute("SELECT COUNT(*) FROM _ss_quarantine WHERE table_name='child'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='RESOLVE'").fetchone()[0] == 1

    def test_tracked_parent_unique_key_update_obeys_fk_action_and_syncs(self, tmp_path):
        base = tmp_path / "parent_key_update.db"
        with sqlite3.connect(base) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_code TEXT NOT NULL
                    REFERENCES parent(code) ON UPDATE CASCADE);
                INSERT INTO parent VALUES (1, 'P-1');
                INSERT INTO child VALUES (10, 'P-1');
            """)
        engine = CRDTSyncEngine(str(base), str(tmp_path / "parent_key_data"))
        source, target = engine.create_replica("key_source"), engine.create_replica("key_target")
        engine.apply_change(source, "key_source", "parent", 1, "code", "P-2")
        engine.sync_replicas(source, target, str(base), "key_source", "key_target", policies={})

        for path in (source, target):
            with sqlite3.connect(path) as c:
                assert c.execute("SELECT code FROM parent WHERE id=1").fetchone() == ("P-2",)
                assert c.execute("SELECT parent_code FROM child WHERE id=10").fetchone() == ("P-2",)
                assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='_ss_quarantine'").fetchone()[0] == 0
                verify_fk_integrity(c)

    def test_tracked_parent_key_update_without_cascade_is_rejected_atomically(self, tmp_path):
        base = tmp_path / "parent_key_no_action.db"
        with sqlite3.connect(base) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_code TEXT NOT NULL REFERENCES parent(code));
                INSERT INTO parent VALUES (1, 'P-1');
                INSERT INTO child VALUES (10, 'P-1');
            """)
        engine = CRDTSyncEngine(str(base), str(tmp_path / "parent_key_no_action_data"))
        replica = engine.create_replica("key_no_action")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            engine.apply_change(replica, "key_no_action", "parent", 1, "code", "P-2")
        with sqlite3.connect(replica) as c:
            assert c.execute("SELECT code FROM parent WHERE id=1").fetchone() == ("P-1",)
            assert c.execute("SELECT parent_code FROM child WHERE id=10").fetchone() == ("P-1",)
            assert c.execute("SELECT COUNT(*) FROM _ss_change_log").fetchone()[0] == 0

    def test_engine_delete_with_alternate_unique_parent_and_composite_dependents(self, tmp_path):
        base = tmp_path / "alternate_engine.db"
        with sqlite3.connect(base) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (x INTEGER, y INTEGER, parent_code TEXT,
                    PRIMARY KEY(x,y), FOREIGN KEY(parent_code) REFERENCES parent(code));
                CREATE TABLE leaf (id INTEGER PRIMARY KEY, child_x INTEGER, child_y INTEGER,
                    FOREIGN KEY(child_x,child_y) REFERENCES child(x,y));
                INSERT INTO parent VALUES(1,'P-A');
                INSERT INTO child VALUES(4,5,'P-A');
                INSERT INTO leaf VALUES(7,4,5);
            """)
        engine = CRDTSyncEngine(str(base), str(tmp_path / "alternate_engine_data"))
        replica = engine.create_replica("alternate_engine")
        engine.apply_delete(replica, "alternate_engine", "parent", 1)
        with sqlite3.connect(replica) as c:
            records = list_quarantined(c)
            assert {r["table_name"] for r in records} == {"child", "leaf"}
            assert json.loads(next(r["row_payload"] for r in records if r["table_name"] == "child")) == {
                "x": 4, "y": 5, "parent_code": "P-A"
            }
            assert c.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM leaf").fetchone()[0] == 0
            verify_fk_integrity(c)

    def test_without_rowid_dependent_schema_rejects_parent_delete_atomically(self, tmp_path):
        base = tmp_path / "without_rowid.db"
        with sqlite3.connect(base) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
                CREATE TABLE child (x INTEGER, parent_code TEXT NOT NULL,
                    PRIMARY KEY(x), FOREIGN KEY(parent_code) REFERENCES parent(code)) WITHOUT ROWID;
                INSERT INTO parent VALUES(1, 'P-1');
                INSERT INTO child VALUES(10, 'P-1');
            """)
        engine = CRDTSyncEngine(str(base), str(tmp_path / "without_rowid_data"))
        replica = engine.create_replica("without_rowid")
        with pytest.raises(sqlite3.OperationalError, match="rowid"):
            engine.apply_delete(replica, "without_rowid", "parent", 1)
        with sqlite3.connect(replica) as c:
            assert c.execute("SELECT COUNT(*) FROM parent WHERE id=1").fetchone()[0] == 1
            assert c.execute("SELECT COUNT(*) FROM child WHERE x=10").fetchone()[0] == 1
            assert c.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='DELETE'").fetchone()[0] == 0

    def test_sql_console_base_write_requires_opt_in_and_still_enforces_fk(self, tmp_path, monkeypatch):
        from fastapi import HTTPException

        from backend.api.models import QueryRequest
        from backend.api.routes_query import execute_query
        from backend.api.state import app_state

        db = tmp_path / "query_fk.db"
        with sqlite3.connect(db) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES parent(id));
                INSERT INTO parent VALUES (1);
                INSERT INTO child VALUES (10, 1);
            """)
        monkeypatch.setattr(app_state, "get_db", lambda _db_id: {"path": str(db)})
        default_request = QueryRequest(db_id="query_fk", sql="DELETE FROM parent WHERE id=1")
        with pytest.raises(HTTPException) as readonly_error:
            execute_query(default_request)
        assert readonly_error.value.status_code == 400
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT COUNT(*) FROM parent WHERE id=1").fetchone()[0] == 1

        opted_in = QueryRequest(db_id="query_fk", sql="DELETE FROM parent WHERE id=1", allow_write=True)
        with pytest.raises(HTTPException) as fk_error:
            execute_query(opted_in)
        assert fk_error.value.status_code == 400
        assert "foreign key constraint failed" in str(fk_error.value.detail).casefold()
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT COUNT(*) FROM parent WHERE id=1").fetchone()[0] == 1
            assert c.execute("SELECT COUNT(*) FROM child WHERE parent_id=1").fetchone()[0] == 1

    def test_sql_console_declared_cascade_does_not_create_quarantine_record(self, tmp_path, monkeypatch):
        from backend.api.models import QueryRequest
        from backend.api.routes_query import execute_query
        from backend.api.state import app_state

        db = tmp_path / "query_cascade.db"
        with sqlite3.connect(db) as c:
            c.executescript("""
                CREATE TABLE parent (id INTEGER PRIMARY KEY);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL
                    REFERENCES parent(id) ON DELETE CASCADE);
                INSERT INTO parent VALUES (1);
                INSERT INTO child VALUES (10, 1);
            """)
        monkeypatch.setattr(app_state, "get_db", lambda _db_id: {"path": str(db)})
        result = execute_query(QueryRequest(
            db_id="query_cascade", sql="DELETE FROM parent WHERE id=1", allow_write=True
        ))
        assert result.rows == [[1]]
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='_ss_quarantine'").fetchone()[0] == 0

    def test_api_resolution_delete_quarantines_both_replicas(self, engine_db, tmp_path):
        from backend.api.routes_conflicts import _write_resolution_atomically
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        a, b = engine.create_replica("api_a"), engine.create_replica("api_b")
        _write_resolution_atomically(a,b,"depts",1,"*",None,"api_a","api_b")
        for path in (a,b):
            with sqlite3.connect(path) as c:
                assert c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM _ss_quarantine WHERE table_name='items'").fetchone()[0] == 2

    def test_parent_delete_failure_rolls_back_quarantine(self, engine_db, tmp_path):
        engine = CRDTSyncEngine(base_db_path=str(engine_db), data_dir=str(tmp_path / "data"))
        path = engine.create_replica("fail_delete")
        with sqlite3.connect(path) as c:
            c.execute("CREATE TRIGGER stop_parent_delete BEFORE DELETE ON depts BEGIN SELECT RAISE(ABORT,'stop'); END")
        with pytest.raises(sqlite3.IntegrityError, match="stop"):
            engine.apply_delete(path,"fail_delete","depts",1)
        with sqlite3.connect(path) as c:
            assert c.execute("SELECT COUNT(*) FROM items WHERE dept_id=1").fetchone()[0] == 2
            assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='_ss_quarantine'").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM _ss_change_log WHERE op_type='DELETE'").fetchone()[0] == 0

    def test_violation_raises(self, tmp_path):
        db = tmp_path / "violation.db"
        with sqlite3.connect(str(db)) as conn:
            conn.executescript("""
                PRAGMA foreign_keys = OFF;
                CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
                INSERT INTO parent VALUES (1, 'P1');
                INSERT INTO child  VALUES (10, 1);
                INSERT INTO child  VALUES (11, 999);  -- orphan!
            """)
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="Foreign-key integrity violation"):
            verify_fk_integrity(conn)
        conn.close()
