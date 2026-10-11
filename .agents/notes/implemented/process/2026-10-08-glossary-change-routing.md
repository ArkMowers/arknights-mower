---
title: Task-Aware Governance and Decision Ownership
status: implemented
category: process
date: 2026-10-08
---

# Task-Aware Governance and Decision Ownership

## Problem

A mandatory six-stage workflow and a simplification-specific proposal requirement assign records by skill invocation rather than decision ownership. Same-topic review repairs then create duplicate records, links and lifecycle work. Unconditional glossary synchronization also treats execution rules as definitions and creates approval requests when meanings remain stable. Structural checks cannot establish behavior or semantic correctness.

## Decision

- [Agent Workflow](../../../AGENTS.md#1-task-selection) selects read-only review, local repair, independent design or documentation maintenance. Repository skills own policy; general skills support techniques without a second artifact pipeline. Its implementation preflight searches relevant callers, contracts, decisions, incidents and tests within the affected scope.
- [Record ownership](../../README.md#record-ownership) controls reuse and merge. Local repair evidence can remain in a PR or change report; an independently useful rationale justifies a record. New decisions use an English/Chinese pair with `format: decision` and direct links, while existing triplets retain their format and metadata.
- [Coding Standards](../../../../CODING_STANDARDS.md#1-core-contracts) owns the six global guarantees. Subsystem contracts own named business rules and stable anchors; reviews link to them. All current guarantees use behavior names without a separate identifier or central registration. Frozen historical identifiers remain solely for legacy metadata. Verification follows real callers and the promised observable result, state, persistence, side effect or exception.
- [Lifecycle criteria](../../AGENTS.md#2-lifecycle-taxonomy) determine implemented status from implementation, focused behavior verification and review, independently of Git commit, push or merge status. Proposals can record completed partial work while identifying remaining work.
- [Concept-impact review](../../../../CODING_STANDARDS.md#concept-impact-review) owns the changed and unchanged concept branches. Root and backend directives point to it instead of repeating an unconditional synchronization requirement.
- The [documentation routing rules](../../../skills/mower-doc/references/doc-hierarchy.md#routing-rules) distinguish concept identity from behavioral guarantees, implementation contracts and developer procedures. Definition constraints include the boundaries that identify a concept.
- A justified unchanged-concept review completes the assessment without glossary edits. A changed definition requires an exact bilingual proposal and [explicit glossary approval](../../../../AGENTS.md#4-global-execution-constraints) before writing it, including when the canonical name remains unchanged.
- Review reports record the chosen route and its reason. Existing glossary content supplies definitions rather than a placement precedent for new operational rules.
- Automated success reports record structures, scoped references, enforced relative document links and Avoid-term checks. Legacy changed active records retain test-path and identifier checks. New changed active decisions validate relative local source/test links without importing targets. Workspace scope includes staged, unstaged and untracked files; branch scope uses the supplied comparison base. Historical missing references remain compatibility warnings. Existence is not evidence that tests passed; behavior, ownership, meaning and approval remain review responsibilities.

The adaptation removes the central business registry: 98 bodies already match their owning contracts; the remaining 31 are reconciled against complete subsystem text, preserving the missing vacancy-fill, reconnect, glyph, UI-policy and recognition boundaries. Rules and checklists use names and direct anchors. The six global contracts retain their complete requirements under descriptive headings. The initial migration preserves 134 unique historical identifiers in one compatibility input. Integration onto the latest alpha retains five more identifiers already declared upstream, bringing the frozen set to 139; the pre-existing duplicate business identifier is not given a new meaning. PR instructions also use contract names and links rather than reintroducing numbering.

[Lifecycle bodies](../../README.md#body-by-lifecycle) preserve the problem, real alternatives and costs. Proposed decisions also state observable acceptance and risks; implemented decisions describe the selected reality and consequences; rejected records keep the proposal and its verdict. A transition changes both status and destination body. New-format records receive mechanical section checks in both languages; ownership, actual alternatives and meaningful evidence remain review responsibilities.

Directory READMEs map responsibilities to real source, governing contracts and focused verification: [documentation](../../../../docs/README.md), [backend](../../../../arknights_mower/README.md), [solvers](../../../../arknights_mower/solvers/README.md), [device control](../../../../arknights_mower/utils/device/README.md), [tests](../../../../arknights_mower/tests/README.md) and [scripts](../../../../scripts/README.md). Local device and test AGENTS files add scoped modification and isolation requirements while inheriting their parents. Root directives link the navigation maps; behavioral definitions stay in their existing owners.

## Alternatives considered

Retaining a smaller registry removes copied text but still requires each business rule to acquire a separate identity and each record to maintain hand-linked metadata. The selected approach puts current behavior in contracts and necessary rationale in bilingual decisions. Copying the whole upstream package template would impose runtime-model fields without a corresponding Mower consumer; existing references instead gain actual entries, observable failure handling, offline verification scope and relevant limitations.

Using one abbreviated body for every lifecycle saves template text but conflates proposed behavior with implemented evidence and loses rejection rationale. The selected lifecycle skeletons retain this useful structure without requiring irrelevant technical sections or a new record for every edit.

Adding a README and AGENTS to every folder would create duplicate or empty policy. Entries are added where Mower has a responsibility to locate or an additional local constraint to apply; generated assets and ordinary subfolders do not acquire documents merely for coverage.

## Consequences

Both languages remain maintained. Historical triplets and the frozen identifier file incur compatibility work, accepted to preserve published records rather than rewrite history. Removing new sidecars also removes the separate manual symbol/test inventory; direct links and focused behavior evidence carry the useful references. Structural checks validate only mechanically decidable facts.

## Verification

The combined focused governance and archive suite passes 62 tests and 85 subtests. Ruff checks and formatting pass for the six changed Python files. Real Git fixtures cover scope, format downgrade, different-category names and local link inventories. Negative fixtures establish rejection of incomplete or mixed formats, malformed compatibility data, invalid local source targets and status-only transitions that retain a proposal body. Bilingual lifecycle checks distinguish body sections from frontmatter, code examples and comments. Directory guides are allowed only at the root, lifecycle and category levels. Inventory failures return errors; ignored local leftovers do not block links, while tracked and nonignored new documents remain checked.

Follow-up review-loop, historical-compatibility and fragment repairs pass 69 tests and 104 subtests in the publishing worktree based on alpha `97f4fba5da551030d0c0a839c81383a830a44178`. Actual CLI regressions reject new legacy triplets, added or deleted frozen identifiers and missing or example-only anchors, while preserving historical edits and lifecycle moves. The frozen set matches all 139 baseline declarations. Review of the integrated contracts retains the latest upstream behavior and its exceptions; the PR skill is already part of that baseline.

Recipes now use real DeviceControl, DeviceSession and configuration interfaces, with task navigation and working directories. Static source review checks their names, examples and test selectors. Two fresh read-only agents, without inherited conversation history, locate capture-recovery and shift-state production callers and tests. The capture investigation identifies an existing repair; the scheduling investigation distinguishes a suspicious preparatory write from a reproduced defect and notices a test-scope gap. The prompts and expectations are preserved as navigation cases 8–9. Neither investigation runs behavior tests or implements a repair. These results support navigation and judgment in these cases, rather than game behavior or a measured productivity improvement.

`arknights_mower/tests/verify_governance_tests.py` exercises the real governance CLI, reference validation, actual Git comparison scopes, historical compatibility, malformed metadata and the absence of production-import side effects. It also checks the bounded success report and verifies that each failed gate returns failure while the remaining checks still run.

CI regression tests execute the command declared in the actual documentation workflow against clean committed Git fixtures. PR, push and manual comparisons reject missing references in changed active records while unchanged records keep compatibility warnings. Missing or unavailable bases fail; new branches and manual runs without a base perform the explicit full active audit described in [reference policy](../../AGENTS.md#5-references-and-compatibility).

Review of recent merged changes exposes incomplete migration consumers, stale policy guidance and checks that finish after delivery. The [verification workflow](../../../AGENTS.md#4-verification-and-reporting) now supplies conditional completion criteria for these cases. Checklist entries for held captures and artifact scope ask review questions and link to their contracts. These instructions receive static review; no new agent trial success rate is measured.

The first seven [workflow cases](../../../skills/mower-code-review/evals/evals.json) define tasks and their required isolated fixtures. Read-only before/after rehearsals covered workspace review, same-topic repair with simplification, an existing guarantee, an independent protocol, duplicate documents, stable concepts and a changed definition. Both versions made several correct decisions; the new rules explicitly resolve the old six-stage ownership conflict. Existing sessions retained prior context, and cases shared context within each group. A fresh isolated CLI attempt could not read files under its execution policy, so no fresh-session success rate, weaker-model performance or token improvement is claimed. The hypothetical protocol, document merge and glossary edits were not implemented by those read-only rehearsals.

The [concept-impact recipe](../../../../docs/cookbook/review-glossary-impact.md) retains six narrower semantic cases. Automated structural tests do not claim to evaluate agent decisions.

After those rehearsals, report-action wording was clarified from the actual tap, cache invalidation, capture and email call path. The published cases also make their fixture prerequisites explicit. Those clarifications received source and document review; they were not rerun as fresh agent trials.

This change reuses the concept-impact requirement and existing scanners. It adds no semantic classifier or domain-runtime abstraction and contributes no glossary edits. This legacy record keeps its frozen identifier in the sidecar for compatibility. The report repair used by the evaluation fixtures has its own decision and delivery scope.
