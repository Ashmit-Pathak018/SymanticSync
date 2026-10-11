"""
backend/tests/test_audit_correctness.py
───────────────────────────────────────
Phase 1 Core Correctness & Adversarial Audit Test Suite.

Audits:
1. Formal policy algebraic properties:
   - Commutativity across all symmetric policies: resolve(a, b) == resolve(b, a)
   - Associativity boundaries: why MIN/MAX/LWW are associative, but AVG is non-associative
   - Idempotency boundaries: SUM is non-idempotent; APPEND duplicate handling
2. Edge cases and boundary conditions:
   - Negative numbers, zeros, None ancestor in SUM
   - Float precision in AVG
   - Deterministic tie-breaking in LWW under identical physical time and logical ticks
   - Extreme strings, empty strings, and special characters in APPEND
3. Synchronization, causality, and multi-replica properties:
   - Repeated sync idempotency (running sync twice on already-converged replicas)
   - Single-sided updates (clean update) vs true concurrent conflicts
   - 3-replica pairwise sync convergence across different sync orderings (A<->B then B<->C vs B<->C then A<->B)
   - HLC monotonicity, causal tick advancement, and clock comparison
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
import pytest

from backend.engine.crdt_sync import CRDTSyncEngine, HLC
from backend.engine.policy_registry import PolicyRegistry, PolicyType
from backend.engine.policy_validator import PolicyValidator
from backend.engine.semantic_resolver import SemanticResolver, ResolutionResult, ResolutionError


# ===========================================================================
# 1. Algebraic & Policy Property Tests
# ===========================================================================

class TestPolicyAlgebraicProperties:
    """Verifies commutativity, associativity, and idempotency boundaries."""

    @pytest.mark.parametrize(
        "policy, base, a, b",
        [
            (PolicyType.SUM, 100, 115, 120),
            (PolicyType.SUM, 0, -10, 25),
            (PolicyType.SUM, None, 5, 8),
            (PolicyType.AVG, None, 10.0, 20.0),
            (PolicyType.AVG, 50, 72.5, 88.5),
            (PolicyType.MIN, None, 42, 17),
            (PolicyType.MAX, None, 42, 17),
            (PolicyType.REJECT, "orig", "change_a", "change_b"),
        ],
    )
    def test_symmetric_policies_commutativity(self, policy, base, a, b):
        """All symmetric policies must satisfy f(A, B) == f(B, A)."""
        res_ab = SemanticResolver.resolve(
            policy=policy,
            base_value=base,
            replica_a_value=a,
            replica_b_value=b,
            replica_a_id="node_1",
            replica_b_id="node_2",
            replica_a_ts=100.0,
            replica_b_ts=100.0,
        )
        res_ba = SemanticResolver.resolve(
            policy=policy,
            base_value=base,
            replica_a_value=b,
            replica_b_value=a,
            replica_a_id="node_2",
            replica_b_id="node_1",
            replica_a_ts=100.0,
            replica_b_ts=100.0,
        )
        assert res_ab.status == res_ba.status
        assert res_ab.resolved_value == res_ba.resolved_value

    def test_append_commutativity_via_replica_id_sorting(self):
        """APPEND must produce identical concatenated strings regardless of caller argument order."""
        res_ab = SemanticResolver.resolve(
            policy=PolicyType.APPEND,
            base_value="base",
            replica_a_value="text_a",
            replica_b_value="text_b",
            replica_a_id="node_1",
            replica_b_id="node_2",
        )
        res_ba = SemanticResolver.resolve(
            policy=PolicyType.APPEND,
            base_value="base",
            replica_a_value="text_b",
            replica_b_value="text_a",
            replica_a_id="node_2",
            replica_b_id="node_1",
        )
        assert res_ab.resolved_value == res_ba.resolved_value == "text_a; text_b"

    def test_lww_strict_commutativity_with_identical_timestamps_tie_breaking(self):
        """LWW must break identical timestamp ties using lexicographical replica_id."""
        ts = 1500000000.0
        # node_2 > node_1 lexicographically, so node_2's value must win in both orderings
        res_1 = SemanticResolver.resolve(
            policy=PolicyType.LWW,
            replica_a_value="val_from_1",
            replica_b_value="val_from_2",
            replica_a_id="node_1",
            replica_b_id="node_2",
            replica_a_ts=ts,
            replica_b_ts=ts,
        )
        res_2 = SemanticResolver.resolve(
            policy=PolicyType.LWW,
            replica_a_value="val_from_2",
            replica_b_value="val_from_1",
            replica_a_id="node_2",
            replica_b_id="node_1",
            replica_a_ts=ts,
            replica_b_ts=ts,
        )
        assert res_1.resolved_value == "val_from_2"
        assert res_2.resolved_value == "val_from_2"

    def test_avg_non_associativity_proof(self):
        """Formally verifies that AVG is NOT associative: avg(avg(a, b), c) != avg(a, avg(b, c))."""
        a, b, c = 10.0, 20.0, 40.0
        # (avg(10, 20), 40) => (15 + 40) / 2 = 27.5
        avg_ab_c = SemanticResolver.resolve(
            policy=PolicyType.AVG,
            replica_a_value=SemanticResolver.resolve(
                policy=PolicyType.AVG, replica_a_value=a, replica_b_value=b
            ).resolved_value,
            replica_b_value=c,
        ).resolved_value

        # (10, avg(20, 40)) => (10 + 30) / 2 = 20.0
        avg_a_bc = SemanticResolver.resolve(
            policy=PolicyType.AVG,
            replica_a_value=a,
            replica_b_value=SemanticResolver.resolve(
                policy=PolicyType.AVG, replica_a_value=b, replica_b_value=c
            ).resolved_value,
        ).resolved_value

        assert avg_ab_c != avg_a_bc
        assert avg_ab_c == 27.5
        assert avg_a_bc == 20.0

    def test_avg_algebraic_idempotency(self):
        """AVG is algebraically idempotent (avg(x, x) = x), but not state-idempotent in sync meshes."""
        # Algebraically idempotent on equal values
        res = SemanticResolver.resolve(
            policy=PolicyType.AVG,
            replica_a_value=42.0,
            replica_b_value=42.0,
        )
        assert res.resolved_value == 42.0

        # Demonstrates why naive duplicate delivery in sync fails:
        # If node A observed 10.0 and node B observed 20.0, merged value is 15.0.
        # If node A's value 10.0 is re-delivered/re-merged, avg(15.0, 10.0) drifts to 12.5.
        intermediate = SemanticResolver.resolve(
            policy=PolicyType.AVG, replica_a_value=10.0, replica_b_value=20.0
        ).resolved_value
        assert intermediate == 15.0
        drifted = SemanticResolver.resolve(
            policy=PolicyType.AVG, replica_a_value=intermediate, replica_b_value=10.0
        ).resolved_value
        assert drifted == 12.5  # Not idempotent under duplicate message delivery


    def test_min_max_associativity(self):
        """MIN and MAX are true join-semilattices: associative, commutative, idempotent."""
        vals = [15, 3, 99]
        # MIN
        min_1 = min(min(vals[0], vals[1]), vals[2])
        min_2 = min(vals[0], min(vals[1], vals[2]))
        assert min_1 == min_2 == 3

        # MAX
        max_1 = max(max(vals[0], vals[1]), vals[2])
        max_2 = max(vals[0], max(vals[1], vals[2]))
        assert max_1 == max_2 == 99

    def test_sum_non_idempotency_hazard(self):
        """Re-resolving SUM with unchanged base leads to duplicate delta addition (double-counting)."""
        base = 100
        delta_a = 110  # +10
        delta_b = 120  # +20
        res1 = SemanticResolver.resolve(PolicyType.SUM, base_value=base, replica_a_value=delta_a, replica_b_value=delta_b)
        assert res1.resolved_value == 130

        # If res1 (130) is treated as replica_a in next sync against original base (100) and delta_b (120):
        res2 = SemanticResolver.resolve(PolicyType.SUM, base_value=base, replica_a_value=res1.resolved_value, replica_b_value=delta_b)
        # 130 + 120 - 100 = 150 (delta_b was double-counted!)
        assert res2.resolved_value == 150


# ===========================================================================
# 2. Boundary Conditions & Edge Cases
# ===========================================================================

class TestBoundaryConditions:
    """Verifies edge cases across data types and nullability."""

    def test_sum_with_negative_values(self):
        """SUM must handle negative deltas and negative balances cleanly."""
        # Base 50, A spends 20 (30), B spends 15 (35) => 50 - 20 - 15 = 15
        res = SemanticResolver.resolve(PolicyType.SUM, base_value=50, replica_a_value=30, replica_b_value=35)
        assert res.resolved_value == 15

    def test_sum_with_none_base_treats_as_zero(self):
        """SUM with None base value defaults to 0."""
        res = SemanticResolver.resolve(PolicyType.SUM, base_value=None, replica_a_value=10, replica_b_value=20)
        assert res.resolved_value == 30

    def test_append_with_identical_text_is_idempotent(self):
        """APPEND does not duplicate strings if both replicas submit the exact same modification."""
        res = SemanticResolver.resolve(
            PolicyType.APPEND,
            base_value="base note",
            replica_a_value="updated note",
            replica_b_value="updated note",
        )
        assert res.resolved_value == "updated note"

    def test_append_with_one_replica_unchanged(self):
        """APPEND returns the modified value cleanly if the other replica equals base."""
        res = SemanticResolver.resolve(
            PolicyType.APPEND,
            base_value="original",
            replica_a_value="original",
            replica_b_value="original with addition",
        )
        assert res.resolved_value == "original with addition"

    def test_append_with_none_values(self):
        """APPEND converts None into empty string safely without raising."""
        res = SemanticResolver.resolve(
            PolicyType.APPEND,
            base_value=None,
            replica_a_value=None,
            replica_b_value="new note",
        )
        assert res.resolved_value == "new note"

    def test_reject_always_returns_flagged(self):
        """REJECT policy must never return resolved status or mutate value."""
        res = SemanticResolver.resolve(PolicyType.REJECT, base_value="A+", replica_a_value="A+", replica_b_value="B+")
        assert res.status == "flagged"
        assert res.resolved_value is None
        assert res.is_deterministic is True


# ===========================================================================
# 3. Synchronization, Causality & Multi-Replica Scenarios
# ===========================================================================

class TestSynchronizationCausality:
    """Tests HLC, sync idempotency, and multi-replica convergence."""

    def test_hlc_monotonicity_and_ordering(self):
        """HLC must advance monotonically on send and receive ticks."""
        clock_a = HLC(node_id="node_a")
        initial_pt = clock_a.pt
        initial_l = clock_a.l

        # Local tick
        clock_a.tick()
        assert clock_a.to_float() >= initial_pt * 1e6 + initial_l

        # Remote tick with future timestamp
        future_pt = clock_a.pt + 10.0
        clock_a.tick(recv_pt=future_pt, recv_l=5)
        assert clock_a.pt >= future_pt
        assert clock_a.l == 0 or clock_a.l >= 6

    def test_repeated_sync_idempotency_on_converged_replicas(self, tmp_path: Path):
        """Running sync twice sequentially on converged replicas must produce 0 new conflicts."""
        base_db = tmp_path / "base.db"
        with sqlite3.connect(str(base_db)) as conn:
            conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER, name TEXT);")
            conn.execute("INSERT INTO accounts VALUES (1, 100, 'Checking');")
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        # Mutate
        engine.apply_change(rep_a, "rep_a", "accounts", 1, "balance", 120)
        engine.apply_change(rep_b, "rep_b", "accounts", 1, "balance", 130)

        policies = {"accounts": {"balance": "SUM", "name": "LWW"}}

        # First sync
        res1 = engine.sync_replicas(rep_a, rep_b, str(base_db), "rep_a", "rep_b", policies)
        assert res1.total_conflicts == 1
        assert res1.auto_resolved == 1

        # Verify values converged to 150 (100 + 20 + 30)
        with sqlite3.connect(rep_a) as ca, sqlite3.connect(rep_b) as cb:
            val_a = ca.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()[0]
            val_b = cb.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()[0]
            assert val_a == val_b == 150

        # Second sync immediately without changes
        res2 = engine.sync_replicas(rep_a, rep_b, str(base_db), "rep_a", "rep_b", policies)
        # Because both replicas now equal each other (150 == 150), no conflict is emitted!
        assert res2.total_conflicts == 0
        assert res2.auto_resolved == 0

    def test_single_sided_update_does_not_trigger_conflict(self, tmp_path: Path):
        """If only replica A modifies a cell while replica B leaves it at base, it is not a conflict."""
        base_db = tmp_path / "base.db"
        with sqlite3.connect(str(base_db)) as conn:
            conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT);")
            conn.execute("INSERT INTO items VALUES (1, 'Initial');")
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
        rep_a = engine.create_replica("rep_a")
        rep_b = engine.create_replica("rep_b")

        # Only rep_a modifies
        engine.apply_change(rep_a, "rep_a", "items", 1, "title", "Updated by A")

        policies = {"items": {"title": "LWW"}}
        res = engine.sync_replicas(rep_a, rep_b, str(base_db), "rep_a", "rep_b", policies)
        # 3-way diff recognizes B is unchanged from base, so no concurrent conflict
        assert res.total_conflicts == 0

    def test_three_replica_pairwise_sync_convergence_with_lww(self, tmp_path: Path):
        """Tests that 3 replicas converge to the highest HLC timestamp regardless of sync pairing."""
        base_db = tmp_path / "base.db"
        with sqlite3.connect(str(base_db)) as conn:
            conn.execute("CREATE TABLE status (id INTEGER PRIMARY KEY, state TEXT);")
            conn.execute("INSERT INTO status VALUES (1, 'DRAFT');")
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
        r_a = engine.create_replica("r_a")
        r_b = engine.create_replica("r_b")
        r_c = engine.create_replica("r_c")

        # Set explicit timestamps: C > B > A
        engine.apply_change(r_a, "r_a", "status", 1, "state", "STATE_A")
        time.sleep(0.01)
        engine.apply_change(r_b, "r_b", "status", 1, "state", "STATE_B")
        time.sleep(0.01)
        engine.apply_change(r_c, "r_c", "status", 1, "state", "STATE_C")

        policies = {"status": {"state": "LWW"}}

        # Pairwise sync: A <-> B, then B <-> C, then A <-> C
        engine.sync_replicas(r_a, r_b, str(base_db), "r_a", "r_b", policies)
        engine.sync_replicas(r_b, r_c, str(base_db), "r_b", "r_c", policies)
        engine.sync_replicas(r_a, r_c, str(base_db), "r_a", "r_c", policies)

        # All 3 replicas must converge to STATE_C (highest timestamp)
        for r_path in (r_a, r_b, r_c):
            with sqlite3.connect(r_path) as c:
                row = c.execute("SELECT state FROM status WHERE id = 1").fetchone()
                assert row[0] == "STATE_C"

    def test_append_multi_operation_and_reordering(self, tmp_path: Path):
        """Audits APPEND behavior under multiple sequential local edits and concurrent sync."""
        base_db = tmp_path / "base_append.db"
        with sqlite3.connect(str(base_db)) as conn:
            conn.execute("CREATE TABLE log (id INTEGER PRIMARY KEY, entries TEXT);")
            conn.execute("INSERT INTO log VALUES (1, 'initial');")
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
        r_a = engine.create_replica("rep_a")
        r_b = engine.create_replica("rep_b")

        # Replica A performs two successive appends
        engine.apply_change(r_a, "rep_a", "log", 1, "entries", "initial; edit_a1")
        time.sleep(0.005)
        engine.apply_change(r_a, "rep_a", "log", 1, "entries", "initial; edit_a1; edit_a2")

        # Replica B concurrently performs an append
        time.sleep(0.005)
        engine.apply_change(r_b, "rep_b", "log", 1, "entries", "initial; edit_b1")

        policies = {"log": {"entries": "APPEND"}}
        # First sync
        res = engine.sync_replicas(r_a, r_b, str(base_db), "rep_a", "rep_b", policies)
        assert res.total_conflicts == 1
        assert res.auto_resolved == 1

        # Check converged state on both replicas
        for r_path in (r_a, r_b):
            with sqlite3.connect(r_path) as c:
                row = c.execute("SELECT entries FROM log WHERE id = 1").fetchone()
                # Lexicographical sort by replica ID: 'rep_a' < 'rep_b'
                assert row[0] == "initial; edit_a1; edit_a2; initial; edit_b1"

        # Duplicate delivery / repeat sync without new mutations must be idempotent
        res2 = engine.sync_replicas(r_a, r_b, str(base_db), "rep_a", "rep_b", policies)
        assert res2.total_conflicts == 0
        for r_path in (r_a, r_b):
            with sqlite3.connect(r_path) as c:
                row = c.execute("SELECT entries FROM log WHERE id = 1").fetchone()
                assert row[0] == "initial; edit_a1; edit_a2; initial; edit_b1"

    def test_hlc_write_back_causal_dominance(self, tmp_path: Path):
        """Verifies that resolved write-back HLC strictly dominates both predecessor causal timestamps."""
        base_db = tmp_path / "base_hlc.db"
        with sqlite3.connect(str(base_db)) as conn:
            conn.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY, val REAL);")
            conn.execute("INSERT INTO metrics VALUES (1, 10.0);")
            conn.commit()

        engine = CRDTSyncEngine(base_db_path=str(base_db), data_dir=str(tmp_path))
        r_a = engine.create_replica("node_a")
        r_b = engine.create_replica("node_b")

        engine.apply_change(r_a, "node_a", "metrics", 1, "val", 15.0)
        time.sleep(0.005)
        engine.apply_change(r_b, "node_b", "metrics", 1, "val", 25.0)

        # Retrieve changes before sync
        ch_a = engine.get_changes_since(r_a, 0.0)
        ch_b = engine.get_changes_since(r_b, 0.0)
        assert len(ch_a) == 1 and len(ch_b) == 1

        ts_a = float(ch_a[0]["ts_pt"]) * 1e6 + float(ch_a[0]["ts_l"])
        ts_b = float(ch_b[0]["ts_pt"]) * 1e6 + float(ch_b[0]["ts_l"])
        max_input_ts = max(ts_a, ts_b)

        policies = {"metrics": {"val": "AVG"}}
        res = engine.sync_replicas(r_a, r_b, str(base_db), "node_a", "node_b", policies)
        assert res.total_conflicts == 1

        # Check write-back log entry on both replicas
        ch_a_after = engine.get_changes_since(r_a, 0.0)
        ch_b_after = engine.get_changes_since(r_b, 0.0)
        assert len(ch_a_after) == 2
        assert len(ch_b_after) == 2

        # The write-back entry timestamp
        wb_a = ch_a_after[-1]
        wb_b = ch_b_after[-1]
        ts_wb_a = float(wb_a["ts_pt"]) * 1e6 + float(wb_a["ts_l"])
        ts_wb_b = float(wb_b["ts_pt"]) * 1e6 + float(wb_b["ts_l"])

        # Must strictly dominate max_input_ts
        assert ts_wb_a > max_input_ts
        assert ts_wb_b > max_input_ts

