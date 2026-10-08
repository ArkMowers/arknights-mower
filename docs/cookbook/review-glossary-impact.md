# Reviewing Glossary Impact

Developer recipe for verifying the concept-impact branches of [INV-06](../../CODING_STANDARDS.md#1-core-invariants). The [documentation routing rules](../../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules) define content placement; [root directives](../../AGENTS.md#4-global-execution-constraints) define glossary approval.

## 1. Compare Concepts Before and After

1. Read the request, diff and relevant glossary definitions. Identify the concepts affected by the change.
2. Compare their names, meanings, boundaries and relationships. Include unchanged labels whose definitions change. Distinguish constraints that identify a concept from rules governing an operation.
3. Record the result in the existing decision note or review report. For unchanged concepts, give the reason and identify the relevant contract and focused tests. This result completes the assessment without a glossary edit or glossary approval request.
4. For changed concepts, prepare exact English and Chinese glossary wording, explain the meaning and purpose, and obtain explicit approval for that wording under the root directives before writing it.
5. Run the automated checks and report their scope separately from the concept-impact review:

   ```bash
   python scripts/verify_governance.py
   pytest arknights_mower/tests/verify_governance_tests.py
   ```

## 2. Review Instruction Changes Against These Cases

Treat each case as an isolated hypothetical requirement. Produce a routing decision, supporting reason, proposed document destinations and any required approval; these exercises authorize no production or glossary edits. When evaluating an agent, supply the case input and repository directives first, then compare its response and file diff with the expected result.

| Case | Input | Expected result |
| :--- | :--- | :--- |
| Pending off-shift task | Suppress regenerated exhaustion tasks when a pending complete off-shift arrangement already covers the operators. Dynamic Shift Transition retains its definition. | Scheduling contract and regression tests; no glossary diff or glossary approval request. |
| Planned idle interval | Exclude planned scheduler idle time from same-scene timeout accounting and reset recognition observations when dispatch resumes. Capture Frame and device concepts retain their definitions. | Lifecycle contract and regression tests; no glossary diff or glossary approval request. |
| Group bed preemption | Compare an incoming operator's priority with every unfinished resting member recalled by a bed takeover. Dormitory Bed Priority retains its definition. | Allocation rule, invariant and regression tests; no glossary diff or glossary approval request. |
| New named concept | Introduce Recovery Reservation as a distinct named concept: a claim on a specified bed by a named recovery target before occupancy is confirmed. Assume this name has no existing glossary definition. | Identify the new concept and its relationship to occupancy; prepare exact bilingual definitions and request glossary approval before writing them. Its operational rules also need a contract. |
| Same name, changed boundary | Keep the name Capture Frame but change its defining canvas from fixed 1920×1080 RGB to dimensions determined by each Device Profile. Assume the request proposes changing the corresponding interface contract too. | Identify a definition delta despite the unchanged label; propose bilingual glossary and interface changes, with glossary approval before writing definitions. |
| Numeric setting only | Adjust the default recovery timeout while preserving the finite monotonic deadline, retry limit and scope of Recovery Budget. | Configuration contract and focused tests; no glossary diff or glossary approval request. |

For each case, the review passes only when the selected destination, concept-impact reason and approval decision all match the expected result. For unchanged concepts, an extra glossary proposal is a failure. For changed concepts, writing glossary files before exact approval is a failure. A passed Avoid-term scan supplies no evidence that these semantic decisions are correct.

These are review cases, not an automated agent evaluator. Record actual agent responses and observed file changes when running them; the Python suite verifies automated reporting and gate failures separately.

Decision: [Glossary change routing](../../.agents/notes/implemented/process/2026-10-08-glossary-change-routing.md) ([中文](../../.agents/notes/implemented/process/2026-10-08-glossary-change-routing.zh.md)).
