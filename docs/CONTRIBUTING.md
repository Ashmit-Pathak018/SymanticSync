# SemanticSync — Contributing Guide

**Version:** 1.0

---

## Before You Contribute

Read the following documents first — they govern all contributions:

1. **`agent.md`** — The collaboration contract. 7 rules that apply to all contributors (human and AI).
2. **`docs/ARCHITECTURE.md`** — Understand the system before changing it.
3. **`docs/CODING_STANDARDS.md`** — Style and quality expectations.
4. **`docs/DECISIONS.md`** — Why the system is structured the way it is.

---

## Workflow

### 1. Claim or Create an Issue
Before starting work, ensure there is a GitHub Issue for the task. Tag yourself as assignee.

### 2. Create a Branch
```bash
# Feature
git checkout -b feat/sql-console-comparison-mode

# Bug fix
git checkout -b fix/windows-permission-error

# Documentation
git checkout -b docs/add-known-limitations
```

Branch naming convention: `<type>/<short-description>` — lowercase, hyphens, no spaces.

### 3. Write Code
Follow `docs/CODING_STANDARDS.md`. Run tests frequently:
```bash
python -m pytest backend/tests/ -v --tb=short
```

### 4. Run All Tests Before PR
```bash
# All 56+ tests must pass
python -m pytest backend/tests/ -v
```

No PR will be merged with failing tests.

### 5. Commit with Conventional Commits
```bash
git commit -m "feat: add comparison mode to SQL console"
git commit -m "fix: handle None base_value in SUM resolver"
git commit -m "test: add edge case for AVG with float inputs"
```

### 6. Open a Pull Request

**PR Description must include:**
- What was changed and why
- Link to the issue (`Closes #42`)
- Test results (paste `pytest` output or attach)
- Any design decisions made

**PR Title format:**
```
feat: add SQL console comparison mode for two replicas
```

---

## Code Review Checklist

Before requesting review, verify:

- [ ] All tests pass (`56 passed, 0 failed`)
- [ ] No domain logic added to `backend/engine/`
- [ ] All SQL uses parameterized queries
- [ ] New public functions have type annotations
- [ ] New public functions have docstrings
- [ ] API changes are reflected in `docs/API_SPECIFICATION.md`
- [ ] New features are added to `CHANGELOG.md`
- [ ] Design token colors used (no raw hex in frontend)

---

## Domain Boundary Enforcement

The most critical rule in `agent.md`:

> **Rule 2: Absolute Domain Independence in Core Engine.**
> The `backend/engine/` directory must never contain domain-specific logic. No reference to "inventory", "patients", "blood_type", "SKU", "clinical_notes", or any domain concept.

If a reviewer finds domain logic in the engine, the PR is **rejected**. No exceptions.

---

## Adding a New Policy

1. Add the enum value to `PolicyType` in `policy_registry.py`
2. Add compatible types to `COMPATIBLE_TYPES`
3. Add a description to `PolicyRegistry.list_all()`
4. Add a resolution handler in `SemanticResolver`
5. Add validation tests in `test_validation.py`
6. Add resolution tests in `test_resolution.py` (including commutativity)
7. Update `docs/POLICY_SPECIFICATION.md`

---

## Adding a New Frontend View

1. Create the view component in `frontend/src/views/`
2. Add the route in `App.jsx`
3. Add a nav item in `Sidebar.jsx`
4. All API calls go through `services/api.js` (no inline fetch)
5. All colors use Tailwind token classes

---

## Questions?

Open a GitHub Discussion or ping in the project channel. Do not push directly to `main`.
