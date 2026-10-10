"""
backend/engine/policy_validator.py
────────────────────────────────────
Validates that a requested policy is compatible with a column's normalised type.

Rules:
  SUM, AVG, MIN, MAX → INTEGER, REAL, NUMERIC
  APPEND             → TEXT only
  LWW, REJECT        → any type (wildcard)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.engine.policy_registry import (
    PolicyType,
    compatible_types,
    get_policy,
    is_registered,
)


@dataclass
class ValidationResult:
    """Outcome of a single policy compatibility check."""

    valid: bool
    policy: Optional[Any] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class PolicyValidator:
    """
    Validator for policy ↔ column-type compatibility.
    Supports both class-level and instance-level calls.
    """

    @classmethod
    def validate(
        cls,
        policy: str | None = None,
        normalized_type: str | None = None,
        *,
        table: str = "",
        column: str = "",
        policy_name: str | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """
        Check whether policy is valid for normalized_type.
        Accepts positional args (policy, normalized_type) or keyword args.
        """
        target_policy = policy if policy is not None else policy_name
        target_type = normalized_type if normalized_type is not None else kwargs.get("norm_type")

        if not target_policy:
            return ValidationResult(
                valid=False,
                policy=None,
                error_code="MISSING_POLICY",
                error_message="Policy name is required",
            )

        if hasattr(target_policy, "value"):
            upper_policy = str(target_policy.value).strip().upper()
        else:
            upper_policy = str(target_policy).strip().upper()

        upper_type = str(target_type).strip().upper() if target_type else "TEXT"

        # 1. Policy must be registered
        if not is_registered(upper_policy):
            return ValidationResult(
                valid=False,
                policy=upper_policy,
                error_code="UNKNOWN_POLICY",
                error_message=(
                    f"Policy '{upper_policy}' is not registered. "
                    "Valid policies: SUM, AVG, APPEND, LWW, REJECT, MIN, MAX."
                ),
            )

        # 2. Check type compatibility
        compat = compatible_types(upper_policy)

        # Wildcard: policy accepts any type
        if "*" in compat:
            try:
                enum_val = PolicyType(upper_policy)
            except ValueError:
                enum_val = upper_policy  # type: ignore[assignment]
            return ValidationResult(valid=True, policy=enum_val)

        if upper_type not in compat:
            readable_compat = ", ".join(sorted(compat))
            return ValidationResult(
                valid=False,
                policy=upper_policy,
                error_code="TYPE_INCOMPATIBLE",
                error_message=(
                    f"Policy '{upper_policy}' is incompatible with column type "
                    f"'{upper_type}'. Compatible types: {readable_compat}."
                ),
            )

        try:
            enum_val = PolicyType(upper_policy)
        except ValueError:
            enum_val = upper_policy  # type: ignore[assignment]

        return ValidationResult(valid=True, policy=enum_val)

    @classmethod
    def validate_batch(
        cls, assignments: list[dict]
    ) -> list[ValidationResult]:
        return [
            cls.validate(
                policy=a.get("policy") or a.get("policy_name"),
                normalized_type=a.get("normalized_type") or a.get("type"),
                table=a.get("table", ""),
                column=a.get("column", ""),
            )
            for a in assignments
        ]
