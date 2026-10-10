---
title: ${TITLE}
status: proposed
category: simplification
date: ${DATE}
---

# ${TITLE}

## 1. Context & Identified Complexity
Use this template only for an independently useful simplification decision after checking record ownership. Otherwise update the existing decision or report findings.
Describe the targeted abstraction, its actual callers and the complexity it introduces.

- **Callers Count**: ${CALLER_COUNT} (verified via rg and static call-path inspection; include dynamic and public entry points)
- **Target File(s)**: `arknights_mower/...`

---

## 2. Invariants & Safety Assessment
- **Affected Invariants**: Reference existing relevant guarantees; a new identifier requires an independent guarantee.
- **Behavioral Equivalence**: Explain why removing or inlining this abstraction does not break external contracts or user configuration.

---

## 3. Proposed Simplification Plan
1. Describe the justified change to `${TARGET_SYMBOL}` in `${TARGET_FILE}`.
2. Explain how affected callers retain the contract; one caller alone does not justify removing an abstraction.
3. Preserve tests of observable behavior and update them for the actual call path. Remove only tests whose responsibility no longer exists.

---

## 4. Verification Plan
- Targeted Unit Tests: `pytest arknights_mower/tests/...`
- Gate Execution: `python scripts/verify_governance.py`
