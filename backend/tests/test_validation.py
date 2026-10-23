"""
test_validation.py
==================
Pytest tests for PolicyValidator.
"""

import pytest
from backend.engine.policy_validator import PolicyValidator


def test_valid_combinations():
    assert PolicyValidator.validate("SUM", "INTEGER").valid is True
    assert PolicyValidator.validate("SUM", "REAL").valid is True
    assert PolicyValidator.validate("AVG", "REAL").valid is True
    assert PolicyValidator.validate("APPEND", "TEXT").valid is True
    assert PolicyValidator.validate("LWW", "TEXT").valid is True
    assert PolicyValidator.validate("LWW", "INTEGER").valid is True
    assert PolicyValidator.validate("REJECT", "TEXT").valid is True
    assert PolicyValidator.validate("REJECT", "INTEGER").valid is True
    assert PolicyValidator.validate("MIN", "INTEGER").valid is True
    assert PolicyValidator.validate("MAX", "REAL").valid is True
    for policy in ("MIN", "MAX"):
        for numeric_type in ("INTEGER", "REAL", "NUMERIC"):
            assert PolicyValidator.validate(policy, numeric_type).valid is True


def test_invalid_type_combinations():
    res1 = PolicyValidator.validate("SUM", "TEXT")
    assert res1.valid is False
    assert res1.error_code == "TYPE_INCOMPATIBLE"

    res2 = PolicyValidator.validate("AVG", "TEXT")
    assert res2.valid is False
    assert res2.error_code == "TYPE_INCOMPATIBLE"

    res3 = PolicyValidator.validate("APPEND", "INTEGER")
    assert res3.valid is False
    assert res3.error_code == "TYPE_INCOMPATIBLE"

    for policy in ("MIN", "MAX"):
        result = PolicyValidator.validate(policy, "TEXT")
        assert result.valid is False
        assert result.error_code == "TYPE_INCOMPATIBLE"


def test_unknown_policy():
    res = PolicyValidator.validate("NON_EXISTENT", "INTEGER")
    assert res.valid is False
    assert res.error_code == "UNKNOWN_POLICY"


def test_batch_validation():
    assignments = [
        {"policy": "SUM", "normalized_type": "INTEGER"},
        {"policy": "AVG", "normalized_type": "TEXT"},
        {"policy": "APPEND", "normalized_type": "TEXT"},
    ]
    results = PolicyValidator.validate_batch(assignments)
    assert len(results) == 3
    assert results[0].valid is True
    assert results[1].valid is False
    assert results[2].valid is True
