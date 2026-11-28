# Two-Axis Review Report Template

```markdown
# Code Review Report: [Working Tree / Branch / Commit Range]

- **Scope**: [staged, unstaged and untracked sources, or the actual requested comparison base]
- **Relevant Contracts**: [behavior names and direct authoritative links; existing identifiers where needed for historical references]

## Summary
- **Standards Axis**: [PASS / FAIL] ([X] findings)
- **Spec Axis**: [PASS / FAIL] ([Y] findings)
- **Structural Checks**: [passed / failed / not run; scope stated]
- **Behavior Tests**: [passed / failed / not run; actual commands and observable guarantee]

---

## 1. Standards Findings
*Review against the applicable global standards, affected subsystem contracts and relevant code smells.*

- **[Affected behavior or standard]** (`path/to/file.py:L123`):
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
- Structural commands: [actual results, compatibility warnings and unverified reference types]
- Focused behavior commands: [actual results; file existence alone does not imply execution]
- Semantic review: [record ownership, contract consistency and concept-impact conclusion]
- Remaining uncertainty: [not established by the automated checks]
```
