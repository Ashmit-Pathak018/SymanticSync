"""
test_resolution.py
==================
Pytest tests for SemanticResolver.
"""

import pytest
from backend.engine.semantic_resolver import SemanticResolver, ResolutionError


def test_sum_additive_delta():
    # base=100, replica A added 15 (115), replica B added 20 (120) => expected 135
    res = SemanticResolver.resolve("SUM", base_value=100, replica_a_value=115, replica_b_value=120)
    assert res.status == "resolved"
    assert res.resolved_value == 135

    # base=0, a=5, b=3 => 8
    res = SemanticResolver.resolve("SUM", base_value=0, replica_a_value=5, replica_b_value=3)
    assert res.resolved_value == 8


def test_sum_commutativity():
    res1 = SemanticResolver.resolve("SUM", base_value=50, replica_a_value=70, replica_b_value=60)
    res2 = SemanticResolver.resolve("SUM", base_value=50, replica_a_value=60, replica_b_value=70)
    assert res1.resolved_value == res2.resolved_value == 80


def test_avg_mean():
    res = SemanticResolver.resolve("AVG", base_value=70, replica_a_value=75, replica_b_value=69)
    assert res.status == "resolved"
    assert res.resolved_value == 72.0


def test_avg_commutativity():
    res1 = SemanticResolver.resolve("AVG", base_value=0, replica_a_value=10, replica_b_value=20)
    res2 = SemanticResolver.resolve("AVG", base_value=0, replica_a_value=20, replica_b_value=10)
    assert res1.resolved_value == res2.resolved_value == 15.0


def test_append_text():
    res = SemanticResolver.resolve(
        "APPEND",
        base_value="init",
        replica_a_value="init; note A",
        replica_b_value="init; note B",
        replica_a_id="node_1",
        replica_b_id="node_2",
    )
    assert res.status == "resolved"
    assert "note A" in res.resolved_value
    assert "note B" in res.resolved_value


def test_append_one_sided_change():
    res = SemanticResolver.resolve(
        "APPEND",
        base_value="base text",
        replica_a_value="base text",
        replica_b_value="base text with edit",
    )
    assert res.resolved_value == "base text with edit"


def test_lww_timestamps():
    # Higher timestamp wins
    res1 = SemanticResolver.resolve(
        "LWW",
        base_value="old",
        replica_a_value="from_a",
        replica_b_value="from_b",
        replica_a_ts=100.0,
        replica_b_ts=200.0,
    )
    assert res1.resolved_value == "from_b"

    res2 = SemanticResolver.resolve(
        "LWW",
        base_value="old",
        replica_a_value="from_a",
        replica_b_value="from_b",
        replica_a_ts=300.0,
        replica_b_ts=200.0,
    )
    assert res2.resolved_value == "from_a"


def test_lww_tie_break():
    # Same timestamp: higher replica_id wins deterministically
    res = SemanticResolver.resolve(
        "LWW",
        base_value="old",
        replica_a_value="val_a",
        replica_b_value="val_b",
        replica_a_id="device_b",
        replica_b_id="device_a",
        replica_a_ts=100.0,
        replica_b_ts=100.0,
    )
    assert res.resolved_value == "val_a"


def test_min_and_max():
    res_min = SemanticResolver.resolve("MIN", base_value=10, replica_a_value=5, replica_b_value=8)
    assert res_min.resolved_value == 5

    res_max = SemanticResolver.resolve("MAX", base_value=10, replica_a_value=5, replica_b_value=8)
    assert res_max.resolved_value == 8


def test_reject_policy():
    res = SemanticResolver.resolve("REJECT", base_value="A+", replica_a_value="A+", replica_b_value="O+")
    assert res.status == "flagged"
    assert res.resolved_value is None
