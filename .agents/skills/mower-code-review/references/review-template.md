# Two-Axis Review Report Template

```markdown
# Code Review Report: [Branch / Commit Range]

## Summary
- **Standards Axis**: [PASS / FAIL] ([X] findings)
- **Spec Axis**: [PASS / FAIL] ([Y] findings)
- **Verification Gates**: [PASS / FAIL] (harness gates & targeted unit tests)

---

## 1. Standards Findings
*Review against CODING_STANDARDS.md invariants [INV-01]-[INV-06] and Fowler smells.*

- **[INV-XX Violation / Baseline Smell]** (`path/to/file.py:L123`):
  - Description: ...
  - Remediation: ...

---

## 2. Spec Findings
*Review against subsystem specification (docs/subsystems/) or technical note.*

- **[Scope Creep / Missing Requirement / Mismatched Behavior]**:
  - Description: ...
  - Remediation: ...

---

## 3. Automated Verification Evidence
- `python scripts/verify_governance.py`: [0 errors]
- Targeted unit tests (`pytest arknights_mower/tests/...`): [All passed]
```
