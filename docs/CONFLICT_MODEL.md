# SemanticSync — Conflict Model

**Version:** 1.0

---

## 1. What is a Conflict?

In SemanticSync, a **conflict** is a **concurrent divergence**: a situation where two independent replicas (A and B) have both modified the same cell relative to a shared base state, and the resulting values differ.

```
                    Base State
                   ┌──────────┐
                   │ qty = 100│
                   └────┬─────┘
            ┌───────────┴───────────┐
            ▼                       ▼
     Replica A writes         Replica B writes
      qty = 115 (+15)          qty = 120 (+20)
            │                       │
            └───────────┬───────────┘
                        ▼
              ⚡ CONFLICT DETECTED
              base=100, a=115, b=120
```

**Not a conflict:**
- Only one replica changed the value (the other kept the base) → clean update, no conflict.
- Both replicas changed to the **same** value → idempotent, no conflict.

---

## 2. Conflict Detection Algorithm

`ConflictDetector.detect()` performs a three-way comparison:

```python
for table in base_tables:
    for row in base_rows:
        for column in non_pk_columns:
            base_val = base_db[table][row][column]
            a_val    = replica_a_db[table][row][column]
            b_val    = replica_b_db[table][row][column]

            if a_val != base_val and b_val != base_val and a_val != b_val:
                # True concurrent conflict
                yield ConflictInfo(...)
```

This correctly distinguishes:
- `a_val == base_val` → A didn't change it → no conflict, B's value is authoritative
- `b_val == base_val` → B didn't change it → no conflict, A's value is authoritative
- Both changed, same value → no conflict (converged naturally)
- **Both changed, different values → ⚡ CONFLICT**

---

## 3. ConflictInfo Data Model

```python
@dataclass
class ConflictInfo:
    conflict_id: str        # UUID4 — unique identifier
    table: str              # SQLite table name
    row_id: Any             # Primary key value
    column: str             # Column name
    base_value: Any         # Value in the common base snapshot
    replica_a_value: Any    # Diverged value in Replica A
    replica_b_value: Any    # Diverged value in Replica B
    replica_a_id: str       # Logical name of Replica A
    replica_b_id: str       # Logical name of Replica B
    replica_a_ts: float     # HLC timestamp of Replica A's write
    replica_b_ts: float     # HLC timestamp of Replica B's write
    detected_at: str        # ISO-8601 UTC detection timestamp
```

---

## 4. Conflict Lifecycle

```
          Detected
              │
              ▼
        ┌──────────┐
        │  pending  │  ← Stored in MergeManager, not yet resolved
        └─────┬─────┘
              │
    ┌─────────┴──────────┐
    │                    │
    ▼                    ▼
┌────────┐          ┌─────────┐
│resolved│          │ flagged │  ← REJECT policy or validation failure
└────────┘          └────┬────┘
                         │
                         ▼
                   Manual Review
                  (pick_a / pick_b / custom)
                         │
                         ▼
                     resolved
```

### Status Values
| Status | Meaning |
|---|---|
| `pending` | Detected but not yet processed |
| `resolved` | Automatically resolved by policy |
| `flagged` | Rejected by `REJECT` policy; awaiting human decision |

---

## 5. Resolution Modes

When resolving via `POST /api/v1/conflicts/resolve`:

| Mode | Description |
|---|---|
| `auto` | Use the assigned policy from AppState (calls `SemanticResolver`) |
| `pick_a` | Accept Replica A's value unconditionally |
| `pick_b` | Accept Replica B's value unconditionally |
| `custom` | Supply a custom resolved value directly |

---

## 6. Conflict Storage

Conflicts are persisted in two places:
1. **`AppState.conflicts`** — in-memory dict (`conflict_id → dict`) backed by `data/registry.json`
2. **`MergeManager`** — optional secondary store at `data/conflicts.json`

Both stores keep full conflict records including both replica values and resolution history.

---

## 7. Write-Back Safety

When a conflict is resolved (either automatically or manually), the resolved value is written back to **both** replicas using parameterized SQL:

```python
conn.execute(
    f'UPDATE "{table}" SET "{column}" = ? WHERE id = ?',
    (resolved_value, row_id)
)
```

**REJECT conflicts are never written back** — replicas remain in their diverged state until a human makes a decision.

---

## 8. Concurrent vs. Sequential Changes

| Scenario | Conflict? | Resolution |
|---|---|---|
| A=110, B=base(100) | No | Take A's value |
| A=base(100), B=120 | No | Take B's value |
| A=115, B=115 (same) | No | Values already agree |
| A=115, B=120 (different) | **Yes** | Apply policy |
| A=115, B=115 but base=100 | No | Both changed to same — no conflict |

---

## 9. Primary Key Conflicts

SemanticSync currently does **not** resolve PRIMARY KEY conflicts (row insertions with the same PK). The conflict detector operates on existing rows only (UPDATE divergences).

Schema-level constraints (NOT NULL, CHECK) are not enforced during write-back — they remain the responsibility of the application layer.
