"""Selected N=3/5 BOUNDED_SUM mesh schedules; no general convergence claim."""

from __future__ import annotations

import itertools
import sqlite3

import pytest

from backend.engine.crdt_sync import CRDTSyncEngine


POLICY = "BOUNDED_SUM[min=0,max=100]"


def _world(tmp_path, n):
    base = tmp_path / "base.db"
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        conn.execute("INSERT INTO counters VALUES (1, 50)")
        conn.commit()
    data_dir = tmp_path / "replicas"
    engine = CRDTSyncEngine(str(base), str(data_dir))
    replicas = [engine.create_replica(f"r{i}") for i in range(n)]
    deltas = [8, -4, 6, -3, 2][:n]
    op_ids = []
    for i, (path, delta) in enumerate(zip(replicas, deltas)):
        op_ids.append(engine.apply_change(
            path, f"r{i}", "counters", 1, "amount", 50 + delta,
            bounded_bounds=(0, 100),
        ))
    return base, data_dir, engine, replicas, deltas, op_ids


def _read(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT amount FROM counters WHERE id=1").fetchone()[0]


def _schedule(n, topology):
    if topology == "star":
        return [(0, other) for other in range(1, n)]
    if topology == "ring":
        return [(i, (i + 1) % n) for i in range(n)]
    if topology == "complete":
        return list(itertools.combinations(range(n), 2))
    raise AssertionError(topology)


@pytest.mark.parametrize("n", [3, 5])
@pytest.mark.parametrize("topology", ["star", "ring", "complete"])
@pytest.mark.parametrize("reverse", [False, True])
def test_mesh_topologies_reversed_order_duplicates_and_restart(tmp_path, n, topology, reverse):
    base, data_dir, engine, replicas, deltas, op_ids = _world(tmp_path, n)
    edges = _schedule(n, topology)
    if reverse:
        edges = [(b, a) for a, b in reversed(edges)]
    policies = {"counters": {"amount": POLICY}}

    split = max(1, len(edges) // 2)
    for a, b in edges[:split]:
        engine.sync_replicas(replicas[a], replicas[b], str(base), f"r{a}", f"r{b}", policies)

    # All operation IDs and signed deltas are durable across process recreation.
    engine = CRDTSyncEngine(str(base), str(data_dir))
    for a, b in edges[split:]:
        engine.sync_replicas(replicas[a], replicas[b], str(base), f"r{a}", f"r{b}", policies)

    # Duplicate delivery of every scheduled edge must create no duplicate receipt.
    for a, b in edges:
        engine.sync_replicas(replicas[a], replicas[b], str(base), f"r{a}", f"r{b}", policies)

    expected = 50 + sum(deltas)
    assert min(deltas) >= -50 and expected == (60 if n == 3 else 59)
    assert [_read(path) for path in replicas] == [expected] * n
    for path in replicas:
        with sqlite3.connect(path) as conn:
            received = conn.execute(
                "SELECT origin_id,COUNT(*) FROM _ss_change_log "
                "WHERE bounded_delta IS NOT NULL GROUP BY origin_id"
            ).fetchall()
            assert {origin for origin, _ in received} == set(op_ids)
            assert all(count == 1 for _, count in received)
