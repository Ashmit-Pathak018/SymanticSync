"""
backend/engine/semantic_resolver.py
──────────────────────────────────────
Deterministic semantic conflict resolution engine.

Applies the merge policy registered for a given (table, column) to produce a
ResolutionResult from (base_value, value_a, value_b).

Policies
--------
  SUM    : resolved = base + (a - base) + (b - base) = a + b - base
  AVG    : resolved = (a + b) / 2.0
  APPEND : resolved = "<a_val>; <b_val>" (ordered deterministically)
  LWW    : resolved = value with higher timestamp; tie-break by replica_id
  REJECT : status = 'flagged', resolved_value = None
  MIN    : resolved = min(a, b)
  MAX    : resolved = max(a, b)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from backend.engine.policy_registry import PolicyType, is_registered


class ResolutionError(ValueError):
    """Raised when a policy cannot be applied to the given values."""


@dataclass
class ResolutionResult:
    """Detailed outcome of a semantic merge operation."""

    status: Literal["resolved", "flagged"]
    resolved_value: Any
    policy: Any
    explanation: str
    is_deterministic: bool = True

    # Allow unpack or scalar equality check if needed
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ResolutionResult):
            return (
                self.status == other.status
                and self.resolved_value == other.resolved_value
                and str(self.policy) == str(other.policy)
            )
        # If compared directly against a scalar value:
        return self.resolved_value == other


class SemanticResolver:
    """
    Deterministic semantic resolver.
    Usable both as class methods and instance methods.
    """

    @classmethod
    def resolve(
        cls,
        policy: str | PolicyType,
        base_value: Any = None,
        replica_a_value: Any = None,
        replica_b_value: Any = None,
        replica_a_id: str = "replica_a",
        replica_b_id: str = "replica_b",
        replica_a_ts: Optional[float] = None,
        replica_b_ts: Optional[float] = None,
        # Aliases
        value_a: Any = None,
        value_b: Any = None,
        timestamp_a: Optional[float] = None,
        timestamp_b: Optional[float] = None,
        **kwargs: Any,
    ) -> ResolutionResult:
        val_a = replica_a_value if replica_a_value is not None else value_a
        val_b = replica_b_value if replica_b_value is not None else value_b
        ts_a = replica_a_ts if replica_a_ts is not None else timestamp_a
        ts_b = replica_b_ts if replica_b_ts is not None else timestamp_b

        pol_str = policy.value if hasattr(policy, "value") else str(policy)
        upper = pol_str.strip().upper()

        if not is_registered(upper):
            raise ResolutionError(f"Unknown policy: '{policy}'")

        if upper == "REJECT":
            return ResolutionResult(
                status="flagged",
                resolved_value=None,
                policy=policy,
                explanation=f"Policy REJECT triggered on conflicting values: {val_a!r} vs {val_b!r}. Flagged for manual review.",
                is_deterministic=True,
            )

        if upper == "SUM":
            try:
                base = 0 if base_value is None else base_value
                a = 0 if val_a is None else val_a
                b = 0 if val_b is None else val_b
                resolved = a + b - base
                # Preserve int type if all inputs were integers
                if isinstance(base, int) and isinstance(a, int) and isinstance(b, int):
                    resolved = int(resolved)
                explanation = f"SUM additive merge: base={base}, delta_a={a - base:+}, delta_b={b - base:+} => {resolved}"
                return ResolutionResult(
                    status="resolved",
                    resolved_value=resolved,
                    policy=policy,
                    explanation=explanation,
                    is_deterministic=True,
                )
            except Exception as exc:
                raise ResolutionError(f"SUM failed: {exc}") from exc

        if upper == "AVG":
            try:
                a = float(val_a)
                b = float(val_b)
                resolved = (a + b) / 2.0
                explanation = f"AVG mean merge: ({a} + {b}) / 2.0 => {resolved}"
                return ResolutionResult(
                    status="resolved",
                    resolved_value=resolved,
                    policy=policy,
                    explanation=explanation,
                    is_deterministic=True,
                )
            except Exception as exc:
                raise ResolutionError(f"AVG requires numeric values: {exc}") from exc

        if upper == "APPEND":
            str_a = "" if val_a is None else str(val_a)
            str_b = "" if val_b is None else str(val_b)
            base_str = "" if base_value is None else str(base_value)

            if str_a == str_b:
                resolved = str_a
                explanation = f"APPEND: identical values from both replicas: {resolved!r}"
            elif str_a == base_str and str_b != base_str:
                resolved = str_b
                explanation = f"APPEND: replica A unchanged from base, accepted replica B: {resolved!r}"
            elif str_b == base_str and str_a != base_str:
                resolved = str_a
                explanation = f"APPEND: replica B unchanged from base, accepted replica A: {resolved!r}"
            else:
                # Deterministic concatenation ordered by replica_id
                if replica_a_id <= replica_b_id:
                    resolved = f"{str_a}; {str_b}"
                else:
                    resolved = f"{str_b}; {str_a}"
                explanation = f"APPEND: joined contributions in replica-id order: {resolved!r}"

            return ResolutionResult(
                status="resolved",
                resolved_value=resolved,
                policy=policy,
                explanation=explanation,
                is_deterministic=True,
            )

        if upper == "LWW":
            chosen = val_a
            winner = replica_a_id
            if ts_a is not None and ts_b is not None:
                if ts_a > ts_b:
                    chosen = val_a
                    winner = replica_a_id
                elif ts_b > ts_a:
                    chosen = val_b
                    winner = replica_b_id
                else:
                    # Timestamp tie: lexicographic replica ID
                    if replica_a_id >= replica_b_id:
                        chosen = val_a
                        winner = replica_a_id
                    else:
                        chosen = val_b
                        winner = replica_b_id
            else:
                if replica_a_id >= replica_b_id:
                    chosen = val_a
                    winner = replica_a_id
                else:
                    chosen = val_b
                    winner = replica_b_id

            explanation = f"LWW: replica {winner} won (ts_a={ts_a}, ts_b={ts_b}) => {chosen!r}"
            return ResolutionResult(
                status="resolved",
                resolved_value=chosen,
                policy=policy,
                explanation=explanation,
                is_deterministic=True,
            )

        if upper == "MIN":
            try:
                resolved = min(val_a, val_b)
                return ResolutionResult(
                    status="resolved",
                    resolved_value=resolved,
                    policy=policy,
                    explanation=f"MIN: min({val_a}, {val_b}) => {resolved}",
                    is_deterministic=True,
                )
            except Exception as exc:
                raise ResolutionError(f"MIN failed: {exc}") from exc

        if upper == "MAX":
            try:
                resolved = max(val_a, val_b)
                return ResolutionResult(
                    status="resolved",
                    resolved_value=resolved,
                    policy=policy,
                    explanation=f"MAX: max({val_a}, {val_b}) => {resolved}",
                    is_deterministic=True,
                )
            except Exception as exc:
                raise ResolutionError(f"MAX failed: {exc}") from exc

        raise ResolutionError(f"No handler implemented for policy '{upper}'")

    @classmethod
    def resolve_value(cls, *args: Any, **kwargs: Any) -> Any:
        res = cls.resolve(*args, **kwargs)
        return res.resolved_value
