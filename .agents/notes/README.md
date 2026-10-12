# Agent Notes

An Agent Note records an independently useful decision: why Mower chooses an approach, which real alternatives it rejects, and which costs it accepts. Current behavior belongs in its subsystem contract; code and focused tests establish implementation. A record connects those owners to reasons that would otherwise be lost.

## Record Ownership

Create a record only when code, tests and existing documentation do not adequately explain durable decision rationale. A record belongs to that decision, not to a date, category, skill invocation or session. Before drafting, search active records using the problem, behavior name, affected symbols and governing contract; inspect candidates rather than deciding from filenames or metadata alone.

Ordinary repairs, additional tests and implementation steps keep reproduction and verification evidence in the change or PR report. Update the existing owner when same-decision work changes its rationale, relevant references or recorded evidence. Keep its original date, category and format; change lifecycle only when the decision's actual state changes. An independent new choice needs independently useful rationale. Read-only findings can remain in a review report.

When a new decision replaces an old one, state their relationship and repair direct links in the same change. Partial supersession retains both records and explains which responsibilities each still owns. Full consolidation preserves every unique rationale, real alternative, consequence, required verification and named coverage gap in the surviving owner; preserve valid legacy metadata where applicable. Do not rewrite an old choice into its opposite or rely on Git history as the only copy of its reasons.

An uncommitted redundant record can be removed after its valid content and links are incorporated into its owner. Inspect Git history before removing a published record: preserve independently useful reasons, and archive meaningful history when its decision no longer guides current work. Limit cleanup to the records selected for the task.

## Lifecycle Criteria

Records live at `{lifecycle}/{category}/YYYY-MM-DD-slug`:

- `proposed`: A decision under consideration, not fully implemented or verified. Partial work and results may be recorded, with remaining acceptance and uncertainty explicit.
- `implemented`: The selected behavior exists, focused behavior verification and relevant structural checks pass, and review confirms the recorded decision and scope. Commit, push and merge states are separate from this assessment.
- `archived`: A completed implementation no longer provides useful guidance for current work, but its reasons have historical value. A replacement is linked when one exists; active contracts refer to their current owner.
- `rejected`: A proposal was considered and declined. Keep it while its reason prevents a plausible, meaningful mistake; explain what evidence or changed conditions would justify considering it again.

Archive completed implementations rather than live proposals. An obsolete proposal is rejected with an honest reason. Classify future guidance from the alternatives, ownership, persistent-data semantics, failure guarantees and conditions for reconsideration; age, length and a desired record count do not determine lifecycle.

## Categories

Choose one existing category according to the decision:

| Category | Decision subject |
| :--- | :--- |
| `architecture` | Responsibilities, protocols, data ownership or persistence schemas |
| `feature` | User-visible or platform-specific capabilities |
| `bug-fix` | A defect whose resolution contains durable decision rationale |
| `simplification` | Removal of unnecessary code, behavior or abstractions |
| `process` | Development, CI, packaging workflow or repository policy |
| `testing` | Test infrastructure, fixtures or verification strategy |

The category does not require a record: a local fix or cleanup still follows [ownership](#record-ownership). A category change is not a reason to manufacture another decision.

## Record Formats

New records are an English `.md` and an aligned Chinese `.zh.md`, with the same `YYYY-MM-DD-slug` basename. Both use the following frontmatter, with `status` matching the lifecycle, `category` matching the directory, and `date` matching the basename. The date is when the decision was first proposed, rather than the latest repair or state transition. Titles may differ by language; the other fields agree.

```yaml
---
format: decision
title: Descriptive title
status: proposed
category: architecture
date: YYYY-MM-DD
---
```

Copy the applicable [body](#body-by-lifecycle) below, replace prompts with facts, and preserve section alignment between languages. New records require no sidecar, business identifier or hand-maintained symbol/test table. Link to existing contracts, source and tests where they help explain or verify the choice; describe planned files in prose until they exist.

Legacy records without `format` retain the English, Chinese and `.sidecar.json` triplet. Maintain their existing format and valid metadata. A marker or a deleted sidecar does not convert a published triplet into a new record. Mixed formats fail validation; available Git HEAD and comparison-base history also detect removed legacy sidecars. New body checks apply to `format: decision` records; review legacy prose for meaning without bulk reformatting history.

### Legacy Sidecar Schema

```json
{
  "title": "Descriptive Title",
  "status": "implemented",
  "category": "architecture",
  "date": "YYYY-MM-DD",
  "authors": ["AuthorName"],
  "invariants": ["[INV-01]", "[INV-02]"],
  "code_symbols": ["module.path.ClassName"],
  "test_suites": ["path/to/test_file.py"]
}
```

Historical identifiers resolve through the frozen [identifier set](../../scripts/legacy_invariant_ids.json), solely to read old metadata. New business rules use behavior names and links to their governing contracts. Legacy array values remain nonempty strings with the existing invariant syntax; test-suite paths refer to existing repository files. Code symbols are descriptive references reviewed statically, without importing production modules.

<a id="record-content"></a>

## Body by Lifecycle

Each required heading carries actual content. The prompts describe the information needed, not a target word count. A short decision may use one paragraph per section; difficult ownership, migration or algorithm choices may need additional technical sections. Record actual alternatives and evidence rather than inventing them to complete a template.

Use the English headings shown below and these Chinese counterparts. Bespoke technical headings remain free-form.

| English heading | Chinese heading |
| :--- | :--- |
| Problem | 问题 |
| Proposal | 提案 |
| Alternatives considered | 考虑过的替代方案 |
| Acceptance criteria | 验收条件 |
| Risks | 风险 |
| Decision | 决策 |
| Consequences | 后果 |
| Rejection | 拒绝理由 |

### Proposed

Prepend the common frontmatter with `status: proposed`:

```markdown
# Decision title

## Problem
Describe the affected user operation or maintenance problem, the observed evidence and the constraints a solution must respect. Make the problem understandable without already choosing its solution; link to its current contract and relevant source.

## Proposal
State the intended choice and why it addresses the problem. Explain affected responsibilities, caller-visible behavior and the necessary implementation approach. Distinguish intended behavior from partial work already observed.

## Alternatives considered
For each genuinely considered approach, explain what it offers and the concrete reason it loses under the stated constraints. Include retaining the current implementation only when it was evaluated.

## Acceptance criteria
State inputs, observable successful outcomes and relevant failure outcomes that establish completion. Identify focused offline coverage and any game or device observation still needed. Describe planned verification separately from results already obtained.

## Risks
Describe accepted costs, possible failures, compatibility exposure and unresolved choices. Name mitigation or the evidence needed to resolve uncertainty where known; do not turn an unverified assumption into a promise.
```

Add decision-specific technical sections between Proposal and Alternatives when their contents are essential. For Mower, relevant detail can include when observation commits Actual Occupancy, how Projected Occupancy remains isolated, which component owns input or compensation, or how a persisted choice survives failure. A configuration or resource-format change may need migration steps, shipped-file requirements and compatibility limits. Include only subjects affected by this choice, and link complete operational rules to their authoritative homes.

### Implemented

Prepend the common frontmatter with `status: implemented`:

```markdown
# Decision title

## Problem
Retain the motivation and constraints that make the choice understandable. Preserve historical observations as such instead of presenting a repaired defect as current behavior.

## Decision
Describe the implemented choice in present tense, its owner and the caller-visible behavior it establishes. Explain material differences from the proposal where relevant and link current contract, source and related decision owners.

## Alternatives considered
Preserve the real alternatives and why they lose. Keep reasons that would matter if someone considered restoring a removed abstraction or changing the responsibility again.

## Consequences
State concrete benefits and accepted costs, including capability given up, remaining compatibility or failure limits, and conditions that could justify revisiting the decision. Distinguish limits of the chosen behavior from incomplete work.
```

Add `## Verification` / `## 验证` when evidence needs its own explanation: name checks actually run, results, the observable behavior they cover and links to the relevant tests. Separate structural checks from behavior evidence and identify game or device outcomes not observed. A test file's existence is not a successful test result. `## Limitations` / `## 限制` can describe meaningful current gaps; it is not a future-task inventory.

Technical sections remain available where they explain lasting responsibility, failure handling, state commitment or compatibility. Keep plans and step-by-step implementation narration out of implemented records. The headings Proposal, Plan, Migration plan and Acceptance criteria, and their Chinese equivalents, describe unbuilt work and do not belong here. Fold their valid outcomes into Decision, Consequences or observed Verification.

### Rejected

Keep the proposal as it was considered, including relevant design, acceptance and risk sections. Set frontmatter to `status: rejected` and add a Rejection section. When recording a decision already declined, reconstruct only facts supported by the discussion or evidence.

```markdown
# Decision title

## Problem
Retain the problem and constraints that originally motivated the proposal.

## Proposal
Retain the losing approach accurately; rejection does not turn it into the accepted implementation.

## Alternatives considered
Preserve the actual alternatives and tradeoffs that explain why the proposal was declined.

## Rejection
State the verdict and its concrete reason, linking a superseding decision when applicable. Explain the still-plausible mistake this record prevents and the changed conditions or new evidence needed to reconsider it. Make unresolved historical details explicit rather than inventing a fuller decision history.
```

Preserve original Acceptance criteria and Risks where present; they describe the rejected proposal, not current obligations. Update rejection or supersession references when their target moves. Retain the record while its reason helps avoid repeating the choice; review records whose premise no longer exists rather than treating every rejection as permanent guidance.

## Moving between Lifecycles

Update both language bodies for the destination before using the [transition helper](../skills/mower-archive-agent-notes/scripts/archive_note.py). For proposed to implemented, replace Proposal with the observed Decision, preserve alternatives, turn acceptance results and known risks into Verification or Consequences, and remove obsolete plans. Partial implementation stays proposed when required acceptance is incomplete. For rejection, preserve the considered proposal and add its verdict. Archived records retain their implemented decision body, now as historical rationale.

The helper moves files and changes status; it does not write a destination body, run verification or establish state criteria. Moves are sequential, so inspect file locations before retrying an interrupted transition. Repair affected inbound and outbound links, then check the complete result through the [lifecycle skill](../skills/mower-archive-agent-notes/SKILL.md).

Keep active implemented facts aligned when files, names or defaults move. A different choice is a superseding decision, rather than a silent rewrite of the old rationale. An archived record is a historical reference; its body does not define today's runtime behavior. A path move alone is not evidence of implementation.

## References and Verification

Run `python scripts/verify_governance.py` from the repository root for changed records. Report structural checks, observed behavior and semantic review separately: structure does not prove ownership, consistent meaning, implementation or approval.

For changed active records, legacy identifiers and test paths remain strict. New decisions also require local `.py`, `.js`, `.ts` and `.vue` links to existing repository files via relative paths; absolute local file targets are rejected. Unchanged historical and archived/rejected reference failures receive compatibility warnings. Outside Git, active reference checks are strict because no historical baseline can be established. `--all-active` requests a full active-reference audit.

For a branch or commit review, pass `--base <actual-comparison-commit>` to include committed note changes alongside staged, unstaged and untracked changes. GitHub checks use the PR base or prior push SHA. A manual run without a comparison base audits all active references; missing event data or an unavailable supplied base fails the check. A link's existence proves neither that a test ran nor that the evidence establishes the decision.

## Discovery and Links

Discover records by lifecycle/category folders, repository search and direct links from the affected subsystem, postmortem or related note. Preserve links during moves and consolidation. A centralized note index or hand-maintained inventory repeats path metadata and is prohibited.

## Prose and Terminology

Use [domain terms](../../CONTEXT.md), the [prose standard](../skills/mower-prose-standard/SKILL.md) and [documentation placement](../skills/mower-doc/references/doc-hierarchy.md#routing-rules). Describe current behavior in present tense, proposed behavior as intended, and historical observations in their historical context. Preserve modality, failures and constraints that affect a caller's decision. New glossary wording follows [explicit approval](../../AGENTS.md#4-global-execution-constraints).

Never add issue tracker numbers in titles, text, filenames or metadata. Keep full behavioral definitions at their owning contracts; records preserve durable reasons and necessary evidence rather than reproducing the contract or the work session.
