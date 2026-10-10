# Agent Workflow

The [root directives](../AGENTS.md) own standing constraints. This file owns task selection and skill coordination.

## 1. Task Selection

Inspect the request and working-tree state before selecting a workflow. Preserve unrelated edits. Resolve the comparison scope before reviewing code.

| Task | Necessary work | Output and completion |
| :--- | :--- | :--- |
| Read-only review | Inspect the requested scope and its relevant standards, contracts and call paths; run focused offline checks where useful. | Findings with evidence, checks actually run and remaining uncertainty. End without changing code, notes or lifecycle states. |
| Local repair | Reuse the governing contract and existing invariants; repair the real call path and verify its observable behavior. Assess concept impact. | Working change and focused verification; update an existing same-decision triplet when its contract or evidence changes. No new record is required merely to complete this workflow. |
| Independent architecture or contract decision | Compare existing decisions and guarantees. Document an independently useful boundary, responsibility or guarantee before implementation. | One bilingual proposal when record ownership justifies it; implementation, behavior verification, review and only the necessary lifecycle transition. |
| Documentation maintenance | Identify the authoritative home, preserve valid content and metadata, and update affected direct links. | Aligned documents and applicable structural checks. No code tests, new invariant or new record solely because documentation changed. |

A local repair that reveals an independent contract decision moves that decision through the third workflow; the rest of the repair retains its original scope. A justified decision to leave a document, invariant or glossary unchanged is a completed assessment.

### Before Implementation

Before changing production behavior, check relevant prior work within the affected scope:

1. Locate the affected entry points, callers, governing contract and existing invariant identifiers.
2. Follow their direct links and search `notes/proposed/`, `notes/implemented/`, relevant `docs/postmortem/` records and tests using the problem, symbols and invariant identifiers. Inspect matching decisions, known failure modes and test expectations.
3. Use focused Git history for the affected paths when a similar repair, compatibility boundary or unexplained behavior needs context. Follow archived or replacement links when a matching record points to them.
4. Use that evidence to select the record owner and regression checks before editing. If no prior work covers the problem, state that briefly in the work report; the search itself creates no record.

Scale this check to the change. It does not require reading all notes or maintaining a search log. Read-only reviews and documentation maintenance use their own scope in the table above.

## 2. Authority and Record Ownership

- [Coding Standards](../CODING_STANDARDS.md) registers invariant identifiers and their concise guarantees. Subsystem specifications own full interface and operational contracts. Checklists ask how a change preserves them; they link rather than maintain another full definition.
- [Documentation routing](skills/mower-doc/references/doc-hierarchy.md#routing-rules) owns placement of glossary definitions, contracts, procedures and rationale. Existing historical duplication is not a template for new text.
- [Record ownership and lifecycle](notes/AGENTS.md) owns triplet reuse, merge, cleanup and implementation-state criteria. Search `proposed/` and `implemented/` before creating a triplet.
- [INV-06](../CODING_STANDARDS.md#1-core-invariants) owns concept-impact assessment. [Root glossary approval](../AGENTS.md#4-global-execution-constraints) applies only to an actual glossary proposal; semantic decisions are not determined by the Avoid-term scan.

Preserve existing invariant numbers. Extend the existing guarantee and its evidence when it already covers the defect; a new number requires a new independent guarantee. Repair current touchpoints without bulk rewriting historical notes.

## 3. Skill Selection

Use one primary workflow for each responsibility. Repository skills own repository policy; general skills supply techniques, not a second sequence of mandatory artifacts. Honor an explicitly requested general skill while applying repository contracts once.

| Responsibility | Primary repository skill | General-skill relationship |
| :--- | :--- | :--- |
| Code review | [mower-code-review](skills/mower-code-review/SKILL.md) | Generic code-review may supply review technique; keep one comparison scope and one report. |
| Complexity assessment | [mower-find-simplifications](skills/mower-find-simplifications/SKILL.md) | Use diagnosis/design techniques as needed; findings do not automatically create a proposal. |
| Guarantee and test design | [mower-define-invariant](skills/mower-define-invariant/SKILL.md) | Generic testing skills support observable behavior verification; reuse existing guarantees first. |
| Document placement | [mower-doc](skills/mower-doc/SKILL.md) | Domain modeling supplies concept analysis; repository routing and approval remain authoritative. |
| Prose | [mower-prose-standard](skills/mower-prose-standard/SKILL.md) | General prose skills refine wording after placement, without adding records or invariants. |
| Record transition | [mower-archive-agent-notes](skills/mower-archive-agent-notes/SKILL.md) | Use only for an actual lifecycle change; documentation merges can retain state. |

Each selected skill declares inputs, outputs and a completion condition. Read only references relevant to the task. Do not execute the catalog as a pipeline.

## 4. Verification and Reporting

Choose tests from the changed behavior and its real callers. Apply the [verification discipline](../CODING_STANDARDS.md#5-verification-discipline) when designing or reviewing tests. Verify return values, state, persistence, side effects or exceptions as required by the guarantee. A helper tested only against itself is insufficient evidence that a production call path is repaired.

Apply these checks when the change crosses a boundary:

- **File or data-source migration**: Account for readers, writers, generators, archive names, application packaging and OTA starting files. Verify installation from a layout collected by the real packaging code, with only the files shipped to users and the affected platforms' text-file conversions.
- **Policy or default change**: Compare runtime behavior with UI controls, help, FAQ and the active contract on every affected platform. Set test expectations from that contract and verify saved explicit choices and independent settings where relevant.

For documentation or governance changes, run:

```bash
python scripts/verify_governance.py
```

When governance scripts change, also run their focused suite:

```bash
pytest arknights_mower/tests/verify_governance_tests.py
```

Report structural checks, behavior tests and semantic review separately. Structural success does not establish runtime correctness, record independence, contract consistency, glossary approval or implementation status. Missing evidence remains explicit rather than becoming a pass.

When delivery includes merging a PR, verify that every required repository CI check for its current head has completed successfully before merging. Pending, failed or cancelled checks leave that delivery step incomplete. Recheck after the head changes; report unavailable check evidence explicitly.
