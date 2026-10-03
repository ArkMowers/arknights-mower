---
title: ${TITLE}
status: proposed
category: simplification
date: ${DATE}
---

# ${TITLE}

## 1. Context & Identified Complexity
Describe the targeted class or abstraction in `arknights_mower` or `ui`.
Detail why it represents dead weight, redundant indirection, or speculative generality.

- **Callers Count**: ${CALLER_COUNT} (verified via grep/AST analysis)
- **Target File(s)**: `arknights_mower/...`

---

## 2. Invariants & Safety Assessment
- **Affected Invariants**: Reference relevant invariants (`[INV-01]` to `[INV-06]`).
- **Behavioral Equivalence**: Explain why removing or inlining this abstraction does not break external contracts or user configuration.

---

## 3. Proposed Simplification Plan
1. Delete `${TARGET_SYMBOL}` from `${TARGET_FILE}`.
2. Inline necessary logic directly at the remaining callsite.
3. Remove associated legacy unit tests or update test mocks.

---

## 4. Verification Plan
- Targeted Unit Tests: `pytest arknights_mower/tests/...`
- Gate Execution: `python scripts/verify_governance.py`
