"""
backend/engine/policy_registry.py
───────────────────────────────────
Central registry of all supported SemanticSync merge policies.

Policies
--------
  SUM     — additive delta merge for numeric columns
  AVG     — arithmetic mean for numeric columns
  APPEND  — text concatenation for TEXT columns
  LWW     — Last-Write-Wins using supplied timestamp + replica ID
  REJECT  — flag for manual review; no auto-resolution
  MIN     — lower bound for numeric columns
  MAX     — upper bound for numeric columns
"""

from __future__ import annotations

from enum import Enum
import math
import re
from typing import Any


class PolicyType(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    APPEND = "APPEND"
    LWW = "LWW"
    REJECT = "REJECT"
    MIN = "MIN"
    MAX = "MAX"
    BOUNDED_SUM = "BOUNDED_SUM"


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
    return _REGISTRY.get(policy_base_name(name))


def list_policies() -> list[dict[str, Any]]:
    return sorted(_REGISTRY.values(), key=lambda p: p["name"])


def is_registered(name: str) -> bool:
    return policy_base_name(name) in _REGISTRY


def compatible_types(name: str) -> set[str]:
    policy = _REGISTRY.get(policy_base_name(name))
    return policy["compatible_types"] if policy else set()


_BOUNDED_SUM_RE = re.compile(
    r"^BOUNDED_SUM\s*\[\s*min\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*,"
    r"\s*max\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*\]$",
    re.IGNORECASE,
)


def policy_base_name(name: str) -> str:
    """Return a registered base policy name, ignoring bounded parameters."""
    upper = str(name).strip().upper()
    return "BOUNDED_SUM" if upper.startswith("BOUNDED_SUM") else upper


def parse_bounded_sum_bounds(name: str) -> tuple[int | float, int | float]:
    """Parse explicit inclusive bounds from ``BOUNDED_SUM[min=...,max=...]``."""
    match = _BOUNDED_SUM_RE.fullmatch(str(name).strip())
    if not match:
        raise ValueError("BOUNDED_SUM requires explicit bounds: BOUNDED_SUM[min=<number>,max=<number>].")
    values: list[int | float] = []
    for token in match.groups():
        if "." in token:
            value: int | float = float(token)
            if not math.isfinite(value):
                raise ValueError("BOUNDED_SUM bounds must be finite numbers.")
        else:
            # Keep integer bounds exact across the full SQLite INTEGER range;
            # converting through binary64 loses precision above 2**53.
            value = int(token)
        values.append(value)
    minimum, maximum = values
    if minimum > maximum:
        raise ValueError("BOUNDED_SUM minimum bound must be less than or equal to maximum bound.")
    return minimum, maximum


# Pre-register core policies
register_policy(
    name="SUM",
    description="Additive delta merge: applies change from each replica relative to common base. For stock counts, counters, balances.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)

register_policy(
    name="AVG",
    description="Pairwise arithmetic mean (A + B) / 2.0; no sample count or weight is retained.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)

register_policy(
    name="APPEND",
    description=(
        "Pairwise text merge: accepts the changed side when the other matches the base, "
        "returns identical current strings once, otherwise joins full strings with '; ' "
        "in replica-ID order. Does not retain per-contribution identities."
    ),
    compatible_types={"TEXT"},
    symmetric=True,
)

register_policy(
    name="LWW",
    description=(
        "When both timestamps are supplied, selects the greater timestamp and then replica ID on ties; if either is missing, selects by replica ID. "
        "This deterministic order is not proof of causality or semantic preservation."
    ),
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

register_policy(
    name="BOUNDED_SUM",
    description=(
        "Add tracked signed deltas with explicit inclusive bounds using "
        "BOUNDED_SUM[min=<number>,max=<number>]. Unsafe operations stay pending."
    ),
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
