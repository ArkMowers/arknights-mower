---
name: mower-find-simplifications
description: Identify over-engineered abstractions, dead code, single-callsite wrappers, and speculative complexity in Arknights Mower. Documents findings into .agents/notes/proposed/simplification/ triplets.
---

# Mower Find Simplifications

Scans the codebase for simplification candidates and produces evidence-backed proposals.

## 1. Simplification Target Classes

1. **Dead Abstractions**: Wrappers or interfaces with only a single production callsite that add indirection without polymorphism.
2. **Speculative Generality**: Configuration options, helper methods, or hooks with zero active consumers.
3. **Redundant Transformations**: Conversions between intermediate representations that can be passed directly.
4. **Duplicate Fallbacks**: Redundant error handling paths that duplicate standard recovery policies.

## 2. Execution Workflow

### Step 1: Scan & Gather Evidence
For each suspected complexity:
- Count callers across `arknights_mower/` and `ui/src/`.
- Verify if any public API contract or plugin requires the interface.
- Determine line reduction and cognitive load decrease.

### Step 2: Record Proposed Simplification Note
Create a decision note triplet under `.agents/notes/proposed/simplification/`:
- `YYYY-MM-DD-slug.md`
- `YYYY-MM-DD-slug.zh.md`
- `YYYY-MM-DD-slug.sidecar.json`
Detail the target code, caller evidence, proposed replacement, and impact assessment.

### Step 3: Verify Safety
Run targeted tests (`pytest arknights_mower/tests/...`) to ensure the proposed simplification preserves existing invariant guarantees.
