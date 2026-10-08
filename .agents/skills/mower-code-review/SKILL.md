---
name: mower-code-review
description: Execute a two-axis code review for Arknights Mower against documented repository coding standards (invariants [INV-01]-[INV-06], smell baseline) and specification requirements.
---

# Mower Two-Axis Code Review

Evaluates git diffs across two orthogonal axes to ensure architectural integrity without masking defects.

## 1. The Two Axes

1. **Standards Axis**:
   - **Core Invariants**: Does the change respect `[INV-01]` through `[INV-06]`?
   - **Resource Lifecycles**: Are external processes and sockets bounded by monotonic timeouts? Are cleanup compensations registered?
   - **Controlled Language**: Are terms aligned with `CONTEXT.md`? Are all *Avoid* terms absent?
   - **Concept Impact**: Complete `[INV-06]` using the [documentation routing rules](../mower-doc/references/doc-hierarchy.md#routing-rules). Record changed definitions or justify unchanged concepts; check exact glossary approval whenever glossary files change.
   - **Hygiene**: Zero issue numbers (`#xxx`), explicit imports, bounded in-memory collections.
   - **Smell Baseline**: Check for Fowler code smells (Mysterious Name, Duplicated Code, Speculative Generality, etc.).

2. **Spec Axis**:
   - Does the diff fulfill the exact functional specification from the subsystem doc or decision note?
   - Is there scope creep (unrequested behavior)?
   - Are edge cases handled as specified?

## 2. Review Process

1. **Diff Extraction**:
   ```bash
   git diff upstream/alpha...HEAD
   git log upstream/alpha..HEAD --oneline
   ```
2. **Automated Gate Execution**:
   ```bash
   python scripts/verify_governance.py
   pytest arknights_mower/tests/verify_governance_tests.py
   ```
   The gate checks note formats, relative Markdown links and Avoid terms. Concept meaning, document placement and user approval require review of the diff and user instructions. For changes to glossary governance instructions, also review the [concept-impact cases](../../../docs/cookbook/review-glossary-impact.md).
3. **Targeted Unit Test Verification**:
   Execute the specific lightweight test suites covering the modified modules (e.g., `device_session_tests.py`).
4. **Structured Report**:
   Present separate sections for `## Standards Findings` and `## Spec Findings` with clear pass/fail status.
