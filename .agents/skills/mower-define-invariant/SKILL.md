---
name: mower-define-invariant
description: Extract, formulate, register, and scaffold tests for core architectural invariants ([INV-XX]) across Arknights Mower subsystems.
---

# Mower Define Invariant

Guides the extraction, formalization, registration, and test-driven defense of domain invariants.

## 1. When to Use
- Designing a new feature, solver, or driver subsystem.
- Establishing safety boundaries for concurrency, resource lifetimes, or state mutations.
- Preventing regression of a critical bug by converting root-cause guarantees into permanent invariants.

## 2. Invariant Formulation Protocol (4 Steps)

### Step 1: Formulate the Falsifiable Rule
Every invariant must state a deterministic, non-negotiable system guarantee:
- **Identifier**: `[INV-{SUBSYSTEM}-{NUMBER}]` (e.g. `[INV-SCHED-05]`, `[INV-ROGUE-01]`, `[INV-DEV-06]`).
- **Short Name**: 2-5 words title.
- **Contract Statement**: One present-tense sentence defining what must always hold true and what is strictly prohibited.

### Step 2: Declare in Decision Note Triplet
In the feature's proposal note (`.agents/notes/proposed/{category}/{slug}.sidecar.json`), register the identifier:
```json
{
  "invariants": ["[INV-SUBSYSTEM-XX]"]
}
```

### Step 3: Register Across Governance SSOT Touchpoints
An invariant must be registered in three authoritative locations:
1. **Subsystem Specification** (`docs/subsystems/*.md`): Under `## 3. Subsystem Invariants`.
2. **Coding Standards** (`CODING_STANDARDS.md`): Under `## 2. Subsystem Invariants`.
3. **Review Checklist** (`.agents/skills/mower-code-review/references/invariants-checklist.md`): Under the corresponding subsystem section.

### Step 4: Hermetic Unit Test Scaffolding
In `arknights_mower/tests/`, implement an offline, deterministic unit test asserting that violating the invariant immediately produces the expected structured error:
```python
def test_invariant_violation_raises_structured_error(self):
    # Setup violating condition
    # Assert structured verdict / exception
```

## 3. Verification
Verify that the new invariant satisfies all formatting constraints and causes no dead links:
```bash
python scripts/verify_governance.py
pytest arknights_mower/tests/verify_governance_tests.py
```
