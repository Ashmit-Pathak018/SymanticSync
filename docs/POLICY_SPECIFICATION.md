# SemanticSync — Policy Specification

**Version:** 1.0

---

## Overview

A **Semantic Policy** is a declarative annotation assigned to a specific `(table, column)` pair in a registered SQLite database. It instructs the SemanticSync engine how to resolve a concurrent conflict on that field.

Policies are **registered** at the engine level (domain-agnostic) and **assigned** at the schema level by the developer.

---

## Policy Registry

All policies are registered in `backend/engine/policy_registry.py`. New policies can be added via `register_policy()` without modifying the resolver — they must also implement a handler in `semantic_resolver.py`.

---

## Policy Definitions

### `SUM` — Additive Delta Merge

**Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`

**Merge Formula:**
```
resolved = value_a + value_b - base_value
```

This is equivalent to: `base + Δa + Δb` where `Δa = value_a - base` and `Δb = value_b - base`.

**Properties:**
- ✅ Commutative: `resolve(a, b) == resolve(b, a)`
- ✅ Deterministic: no randomness
- ✅ Converges to the sum of all independent increments

**Use Cases:**
- Inventory quantity updates
- Counter increments (edit_count, views, likes)
- Financial balance adjustments

**Example:**
```
base=100, replica_a=115 (+15), replica_b=120 (+20)
→ resolved = 115 + 120 - 100 = 135  ✓
```

---

### `AVG` — Arithmetic Mean

**Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`

**Merge Formula:**
```
resolved = (value_a + value_b) / 2.0
```

**Properties:**
- ✅ Commutative
- ✅ Returns `float` always
- ⚠️ Does not account for base_value (pure mean of the two conflicting values)

**Use Cases:**
- Sensor readings (heart_rate, temperature)
- Ratings and scores
- Dosage values where both readings are valid

**Example:**
```
replica_a=75, replica_b=69
→ resolved = (75 + 69) / 2.0 = 72.0  ✓
```

---

### `APPEND` — Deterministic Text Concatenation

**Compatible Types:** `TEXT`

**Merge Algorithm:**
1. If `value_a == value_b` → return either (no real conflict)
2. If only one side changed from base → return the changed value
3. If both changed → concatenate in `replica_id` lexicographic order: `f"{first}; {second}"`

**Properties:**
- ✅ Commutative (ordering determined by replica_id sort, not call order)
- ✅ Preserves both contributions
- ✅ Idempotent when values are identical

**Use Cases:**
- Clinical notes, meeting notes, log entries
- Collaborative document bodies
- Tag lists, comment threads

**Example:**
```
base="Initial note"
replica_a="Initial note. Alice added: action items."
replica_b="Initial note. Bob added: risks."
→ resolved = "Initial note. Alice added: action items.; Initial note. Bob added: risks."
```

---

### `LWW` — Last-Write-Wins

**Compatible Types:** Any (`*`)

**Merge Algorithm:**
1. Compare `timestamp_a` vs `timestamp_b` (Hybrid Logical Clock floats)
2. Higher timestamp wins
3. **Tie-break:** lexicographically higher `replica_id` wins (deterministic)

**Properties:**
- ✅ Deterministic with tie-breaking
- ❌ Not commutative in general (winner depends on timestamps)
- ⚠️ One value is discarded — acceptable when recency governs meaning

**Use Cases:**
- Profile fields (name, avatar_url)
- Status fields (order_status, account_status)
- Soft-overwrite fields where latest is always correct

---

### `REJECT` — Manual Review Required

**Compatible Types:** Any (`*`)

**Behavior:**
- Never applies any automatic merge
- Returns `ResolutionResult { status="flagged", resolved_value=None }`
- Conflict is stored in `MergeManager` for human review
- No replica value is mutated

**Properties:**
- ✅ Safe — zero data mutation
- ✅ Always deterministic (always flags)
- ✅ Preserves both values for manual inspection

**Use Cases:**
- Critical immutable keys (`sku`, `patient_id`, `blood_type`)
- Fields where any automatic resolution is unsafe
- Regulatory compliance requirements

---

### `MIN` — Minimum Bound

**Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`

```
resolved = min(value_a, value_b)
```

**Use Cases:** Pricing floors, resource limits, SLA thresholds.

---

### `MAX` — Maximum Bound

**Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`

```
resolved = max(value_a, value_b)
```

**Use Cases:** High-water marks, capability scores, inventory ceilings.

---

## Type Compatibility Matrix

| Policy | INTEGER | REAL | NUMERIC | TEXT | BLOB |
|--------|---------|------|---------|------|------|
| SUM    | ✅ | ✅ | ✅ | ❌ | ❌ |
| AVG    | ✅ | ✅ | ✅ | ❌ | ❌ |
| APPEND | ❌ | ❌ | ❌ | ✅ | ❌ |
| LWW    | ✅ | ✅ | ✅ | ✅ | ✅ |
| REJECT | ✅ | ✅ | ✅ | ✅ | ✅ |
| MIN    | ✅ | ✅ | ✅ | ❌ | ❌ |
| MAX    | ✅ | ✅ | ✅ | ❌ | ❌ |

Incompatible assignments return `HTTP 422` with `error_code: "TYPE_INCOMPATIBLE"`.

---

## Validation Rules

```python
# Valid:
PolicyValidator.validate("SUM", "INTEGER")    → valid=True
PolicyValidator.validate("APPEND", "TEXT")    → valid=True
PolicyValidator.validate("REJECT", "BLOB")    → valid=True  # wildcard

# Invalid:
PolicyValidator.validate("SUM", "TEXT")       → valid=False, error_code="TYPE_INCOMPATIBLE"
PolicyValidator.validate("AVG", "TEXT")       → valid=False
PolicyValidator.validate("MAGIC", "INTEGER")  → valid=False, error_code="UNKNOWN_POLICY"
```

---

## Extending the Policy Registry

```python
from backend.engine.policy_registry import register_policy

register_policy(
    name="MEDIAN",
    description="Statistical median of concurrent numeric values.",
    compatible_types={"INTEGER", "REAL", "NUMERIC"},
    symmetric=True,
)
```

Then add the corresponding handler in `SemanticResolver._HANDLERS`.
