# SemanticSync — Policy Specification

**Version:** 2.1 (Phase 1 Follow-Up Corrected)  
**Status:** Implementation-Ready Specification

---

## 1. Overview & Policy Classification

A **Semantic Policy** is a declarative annotation configured for a specific `(table, column)` pair in a registered SQLite database. It dictates the deterministic reconciliation logic applied when concurrent divergent mutations are detected between replicas.

### Formal Algebraic Classification

A general-purpose state-based CRDT merge operator $\sqcup$ must form a join-semilattice satisfying:
1. **Commutativity:** $x \sqcup y = y \sqcup x$
2. **Associativity:** $(x \sqcup y) \sqcup z = x \sqcup (y \sqcup z)$
3. **Idempotency:** $x \sqcup x = x$

In SemanticSync, policies fall into three distinct formal categories:

| Policy | Algebraic Category | Commutative? | Associative? | Idempotent? | Supported Scope |
|---|---|---|---|---|---|
| **`MIN` / `MAX`** | **Join-Semilattice** | ✅ Yes | ✅ Yes | ✅ Yes | Arbitrary N-way pairwise merge |
| **`LWW`** | **Causally-Ordered Register** | ✅ (Deterministic tie-break) | ✅ Yes | ✅ Yes | Global timestamp total order |
| **`REJECT`** | **Safety Guard / Triage** | ✅ Yes | ✅ Yes | ✅ Yes | Always yields flagged state |
| **`SUM` (Delta)**| **Delta Operation (Conditional)** | ✅ Yes | ⚠️ Context-dependent | ❌ No (double-counting risk) | Pairwise sync with ancestor base |
| **`APPEND`** | **Set/List Union (Conditional)** | ✅ (Sorted order) | ⚠️ Sensitive to delimiters | ⚠️ Idempotent on raw elements | Pairwise sync with ancestor base |
| **`AVG`** | **Non-Associative (Restricted)** | ✅ Yes | ❌ **No** | ✅ **Yes†** | Controlled pairwise sync only |

> **†** AVG is algebraically idempotent: $\text{avg}(x, x) = x$ for any scalar $x$. However, _sync-level_ idempotency requires the base snapshot to be refreshed before each application. Repeating the formula on a stale base causes progressive drift (the observed value converges toward the extremes of the distribution with each re-application). Do not conflate operation-level algebraic idempotency with the synchronization property of "applying the same change twice yields the same system state."

---

## 2. Detailed Policy Specifications

### 2.1 `SUM` — Additive Delta Reconciliation

- **Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`
- **Required Inputs:**
  - Common ancestor base value: $V_{\text{base}}$
  - Replica A value: $V_A$
  - Replica B value: $V_B$
- **Mathematical Formula:**
  $$\Delta_A = V_A - V_{\text{base}}, \quad \Delta_B = V_B - V_{\text{base}}$$
  $$V_{\text{resolved}} = V_{\text{base}} + \Delta_A + \Delta_B = V_A + V_B - V_{\text{base}}$$
- **Properties:**
  - **Commutativity:** $V_A + V_B - V_{\text{base}} = V_B + V_A - V_{\text{base}}$ (Verified).
  - **Type Preservation:** If $V_{\text{base}}, V_A, V_B \in \mathbb{Z}$, the result is cast to `int`.
- **Known Limitations & Double-Counting Hazards:**
  - `SUM` is **not idempotent**. Applying the formula multiple times without updating the base snapshot will repeatedly add deltas.
  - In N-way topologies ($A \leftrightarrow B \leftrightarrow C$), delta tracking requires explicit vector logs or PN-Counters rather than scalar 3-way evaluation to avoid cyclic amplification.
  - Unbounded subtractions can violate domain invariants (e.g., negative inventory balances).

---

### 2.2 `AVG` — Arithmetic Mean

- **Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`
- **Required Inputs:**
  - Replica A value: $V_A$
  - Replica B value: $V_B$
- **Mathematical Formula:**
  $$V_{\text{resolved}} = \frac{V_A + V_B}{2.0}$$
- **Properties:**
  - **Commutativity:** $\frac{V_A + V_B}{2} = \frac{V_B + V_A}{2}$ (Verified).
  - **Algebraic Idempotency:** $\text{avg}(x, x) = x$ — applying the operator to two identical values returns the same value.
  - Always returns `float`.
- **Formal Non-Associativity Warning:**
  - **`AVG` is NOT associative:**
    $$\text{avg}(\text{avg}(a, b), c) = \frac{\frac{a+b}{2} + c}{2} = \frac{a}{4} + \frac{b}{4} + \frac{c}{2} \neq \text{avg}(a, \text{avg}(b, c))$$
  - **Sync-Level Idempotency Caveat:** Even though $\text{avg}(x, x) = x$ algebraically, repeated application of the formula against a stale base snapshot (i.e., without refreshing $V_{\text{base}}$ after each sync) causes progressive drift. This is a synchronization protocol property, not an operator property.
  - **Operational Constraint:** `AVG` is strictly supported for pairwise reconciliation where both readings are treated as concurrent independent sensor observations. For true N-replica averaging, the underlying state must track a tuple $\langle \text{sum}, \text{count} \rangle$.

---

### 2.3 `APPEND` — Deterministic Text Concatenation

- **Compatible Types:** `TEXT`
- **Required Inputs:**
  - $V_{\text{base}}, V_A, V_B$, and replica identifiers $\text{id}_A, \text{id}_B$
- **Algorithm:**
  1. If $V_A = V_B$, return $V_A$.
  2. If $V_A = V_{\text{base}}$ and $V_B \neq V_{\text{base}}$, return $V_B$ (one-sided change).
  3. If $V_B = V_{\text{base}}$ and $V_A \neq V_{\text{base}}$, return $V_A$ (one-sided change).
  4. If both diverged:
     - Sort replica IDs lexicographically to guarantee commutativity:
       $$\text{order} = (\text{id}_A, \text{id}_B) \text{ if } \text{id}_A < \text{id}_B \text{ else } (\text{id}_B, \text{id}_A)$$
     - Format: `"{first_value}; {second_value}"`
- **Properties:**
  - **Commutativity:** Guaranteed by sorting on replica identifier.
  - **Idempotency:** When both replicas submit identical text, duplicates are not generated.
- **Limitations:** Delimiter concatenation does not perform character-level operational transformation or collaborative rich-text formatting (use CRDT text sequences like RGA/Fugue for inline document editing).

---

### 2.4 `LWW` — Last-Write-Wins Register

- **Compatible Types:** Any (`INTEGER`, `REAL`, `TEXT`, `BLOB`, `NUMERIC`)
- **Required Inputs:**
  - $V_A, V_B$, HLC timestamps $\tau_A, \tau_B$, and replica identifiers $\text{id}_A, \text{id}_B$
- **Algorithm:**
  1. If $\tau_A > \tau_B$, select $V_A$.
  2. If $\tau_B > \tau_A$, select $V_B$.
  3. If $\tau_A = \tau_B$ (exact tie), select the value corresponding to $\max(\text{id}_A, \text{id}_B)$ lexicographically.
- **Properties:**
  - **Total Order:** Forms a strict join-semilattice over $\langle \tau, \text{id}, V \rangle$.
  - **Commutative, Associative, Idempotent.**
- **Known Failure Mode:** Discards the earlier mutation entirely, resulting in lost concurrent contributions.

---

### 2.5 `REJECT` — Safety Guard / Manual Review

- **Compatible Types:** Any (`*`)
- **Behavior:**
  - Always returns:
    $$\text{ResolutionResult}(\text{status} = \text{"flagged"}, \text{resolved\_value} = \text{None})$$
  - The conflict is durably persisted in `MergeManager` and `AppState`.
  - **Replicas are NOT mutated.** No write-back occurs until manual intervention.
- **Properties:**
  - Trivially commutative and deterministic.
  - Guarantees safety for critical keys, biometrics, or invariant fields where automated resolution is intolerable.

---

### 2.6 `MIN` and `MAX` — Bounded Lattice Extrema

- **Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`
- **Formulas:**
  $$\text{MIN}(V_A, V_B) = \min(V_A, V_B), \quad \text{MAX}(V_A, V_B) = \max(V_A, V_B)$$
- **Properties:**
  - Proven join-semilattices (totally ordered numeric sets).
  - Fully commutative, associative, and idempotent.

---

### 2.7 `BOUNDED_SUM` (Phase 3 Specification)

- **Compatible Types:** `INTEGER`, `REAL`, `NUMERIC`
- **Intended Semantics:**
  - Evaluates standard additive delta: $V_{\text{target}} = V_{\text{base}} + \Delta_A + \Delta_B$.
  - Evaluates explicit invariant condition: $V_{\text{target}} \ge \text{min\_bound}$ (e.g., $0$ for inventory).
  - **Safety Rule:** If $V_{\text{target}} < \text{min\_bound}$, the resolver does NOT write back a negative value. It marks status as `flagged` with error `INVARIANT_VIOLATION: Bound underflow`.

---

## 3. Type Compatibility & Validation Rules

| Policy | INTEGER | REAL | NUMERIC | TEXT | BLOB |
|---|---|---|---|---|---|
| **SUM** | ✅ Compatible | ✅ Compatible | ✅ Compatible | ❌ `TYPE_INCOMPATIBLE` | ❌ `TYPE_INCOMPATIBLE` |
| **AVG** | ✅ Compatible | ✅ Compatible | ✅ Compatible | ❌ `TYPE_INCOMPATIBLE` | ❌ `TYPE_INCOMPATIBLE` |
| **APPEND** | ❌ `TYPE_INCOMPATIBLE` | ❌ `TYPE_INCOMPATIBLE` | ❌ `TYPE_INCOMPATIBLE` | ✅ Compatible | ❌ `TYPE_INCOMPATIBLE` |
| **LWW** | ✅ Compatible | ✅ Compatible | ✅ Compatible | ✅ Compatible | ✅ Compatible |
| **REJECT** | ✅ Compatible | ✅ Compatible | ✅ Compatible | ✅ Compatible | ✅ Compatible |
| **MIN / MAX** | ✅ Compatible | ✅ Compatible | ✅ Compatible | ❌ `TYPE_INCOMPATIBLE` | ❌ `TYPE_INCOMPATIBLE` |

Incompatible configurations are caught by `PolicyValidator` and return `HTTP 422 Unprocessable Entity` with a descriptive message before runtime synchronization.
