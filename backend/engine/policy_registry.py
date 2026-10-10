"""
backend/engine/policy_registry.py
───────────────────────────────────
Central registry of all supported SemanticSync merge policies.

Policies
--------
  SUM     — additive delta merge for numeric columns
  AVG     — arithmetic mean for numeric columns
  APPEND  — text concatenation for TEXT columns
  LWW     — Last-Write-Wins using HLC timestamp + replica ID
  REJECT  — flag for manual review; no auto-resolution
  MIN     — lower bound for numeric columns
  MAX     — upper bound for numeric columns
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class PolicyType(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    APPEND = "APPEND"
    LWW = "LWW"
    REJECT = "REJECT"
    MIN = "MIN"
    MAX = "MAX"


# policy_name → {name, description, compatible_types, symmetric}
_REGISTRY: dict[str, dict[str, Any]] = {}


def register_policy(
    name: str,
    description: str,
    compatible_types: set[str],
    symmetric: bool = True,
) -> None:
    _REGISTRY[name.upper()] = {
        "name": name.upper(),
        "description": description,
        "compatible_types": {t.upper() for t in compatible_types},
        "symmetric": symmetric,
    }


def get_policy(name: str) -> dict[str, Any] | None:
    return _REGISTRY.get(name.upper())


def list_policies() -> list[dict[str, Any]]:
    return sorted(_REGISTRY.values(), key=lambda p: p["name"])


def is_registered(name: str) -> bool:
    return name.upper() in _REGISTRY


def compatible_types(name: str) -> set[str]:
    policy = _REGISTRY.get(name.upper())
    return policy["compatible_types"] if policy else set()


# Pre-register core policies
register_policy(
    name="SUM",
    description="Additive delta merge: applies change from each replica relative to common base. For stock counts, counters, balances.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)

register_policy(
    name="AVG",
    description="Arithmetic mean of all replica values: (A + B) / 2.0. Suitable for sensor readings, ratings, dosages.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)

register_policy(
    name="APPEND",
    description="Concatenates divergent text values with '; ' separator. Preserves both contributions.",
    compatible_types={"TEXT"},
    symmetric=True,
)

register_policy(
    name="LWW",
    description="Last-Write-Wins: selects value with highest logical timestamp. Tie-break via replica ID.",
    compatible_types={"*"},
    symmetric=False,
)

register_policy(
    name="REJECT",
    description="Flags conflicting record for manual review. Critical keys, blood type, ambiguous changes.",
    compatible_types={"*"},
    symmetric=True,
)

register_policy(
    name="MIN",
    description="Deterministic lower-bound: selects minimum of replica values.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)

register_policy(
    name="MAX",
    description="Deterministic upper-bound: selects maximum of replica values.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)


class PolicyRegistry:
    """Wrapper class providing object-oriented access to the registry."""

    PolicyType = PolicyType

    @classmethod
    def get_policy(cls, name: str) -> dict[str, Any] | None:
        return get_policy(name)

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        return list_policies()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return is_registered(name)

    @classmethod
    def compatible_types(cls, name: str) -> set[str]:
        return compatible_types(name)

    @classmethod
    def is_compatible(cls, policy_name: str, normalized_type: str) -> bool:
        types = compatible_types(policy_name)
        return "*" in types or normalized_type.upper() in types
