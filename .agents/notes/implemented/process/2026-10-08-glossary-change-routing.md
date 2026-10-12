---
title: Task-Aware Governance and Decision Ownership
status: implemented
category: process
date: 2026-10-08
---

# Task-Aware Governance and Decision Ownership

## Context

A mandatory six-stage workflow and a simplification-specific proposal requirement assign records by skill invocation rather than decision ownership. Same-topic review repairs then create duplicate records, links and lifecycle work. Unconditional glossary synchronization also treats execution rules as definitions and creates approval requests when meanings remain stable. Structural checks cannot establish behavior or semantic correctness.

## Contract

- [Agent Workflow](../../../AGENTS.md#1-task-selection) selects read-only review, local repair, independent design or documentation maintenance. Repository skills own policy; general skills support techniques without a second artifact pipeline. Its implementation preflight searches relevant callers, contracts, decisions, incidents and tests within the affected scope.
- [Record ownership](../../AGENTS.md#1-record-ownership) governs reuse and merges. Same-topic repair, tests and incidental simplification update the existing triplet; a date, category, skill or session does not justify another record. Merges retain valid bilingual content and metadata. Uncommitted redundant products and historically meaningful records use different cleanup paths.
- [Coding Standards](../../../../CODING_STANDARDS.md#1-core-invariants) registers identifiers and concise guarantees; subsystem contracts own full definitions, and review checklists link to them. Existing guarantees are reused before new independent guarantees are registered. Verification follows real callers and the promised observable result, state, persistence, side effect or exception.
- [Lifecycle criteria](../../AGENTS.md#2-lifecycle-taxonomy) determine implemented status from implementation, focused behavior verification and review, independently of Git commit, push or merge status. Proposals can record completed partial work while identifying remaining work.
- [INV-06](../../../../CODING_STANDARDS.md#1-core-invariants) owns the concept-impact branches. Root and backend directives point to it instead of repeating an unconditional synchronization requirement.
- The [documentation routing rules](../../../skills/mower-doc/references/doc-hierarchy.md#routing-rules) distinguish concept identity from behavioral guarantees, implementation contracts and developer procedures. Definition constraints include the boundaries that identify a concept.
- A justified unchanged-concept review completes the assessment without glossary edits. A changed definition requires an exact bilingual proposal and [explicit glossary approval](../../../../AGENTS.md#4-global-execution-constraints) before writing it, including when the canonical name remains unchanged.
- Review reports record the chosen route and its reason. Existing glossary content supplies definitions rather than a placement precedent for new operational rules.
- Automated success reports only note structures and required references, enforced relative document links and Avoid-term checks. Active changed records require existing test paths and declared invariant identifiers. Workspace scope includes staged, unstaged and untracked files; branch scope uses the supplied comparison base. Historical missing references remain compatibility warnings. Code-symbol existence, metadata overlap, behavior, document placement and approval remain review responsibilities; production modules are not imported to resolve symbols.

## Verification

`arknights_mower/tests/verify_governance_tests.py` exercises the real governance CLI, reference validation, actual Git comparison scopes, historical compatibility, malformed metadata and the absence of production-import side effects. It also checks the bounded success report and verifies that each failed gate returns failure while the remaining checks still run.

CI regression tests execute the command declared in the actual documentation workflow against clean committed Git fixtures. PR, push and manual comparisons reject missing references in changed active records while unchanged records keep compatibility warnings. Missing or unavailable bases fail; new branches and manual runs without a base perform the explicit full active audit described in [reference policy](../../AGENTS.md#5-references-and-compatibility).

Review of recent merged changes exposes incomplete migration consumers, stale policy guidance and checks that finish after delivery. The [verification workflow](../../../AGENTS.md#4-verification-and-reporting) now supplies conditional completion criteria for these cases. Checklist entries for held captures and artifact scope ask review questions and link to their contracts. These instructions receive static review; no new agent trial success rate is measured.

The [workflow cases](../../../skills/mower-code-review/evals/evals.json) define seven tasks and their required isolated fixtures. Read-only before/after rehearsals covered workspace review, same-topic repair with simplification, an existing guarantee, an independent protocol, duplicate documents, stable concepts and a changed definition. Both versions made several correct decisions; the new rules explicitly resolve the old six-stage ownership conflict. Existing sessions retained prior context, and cases shared context within each group. A fresh isolated CLI attempt could not read files under its execution policy, so no fresh-session success rate, weaker-model performance or token improvement is claimed. The hypothetical protocol, document merge and glossary edits were not implemented by those read-only rehearsals.

The [concept-impact recipe](../../../../docs/cookbook/review-glossary-impact.md) retains six narrower semantic cases. Automated structural tests do not claim to evaluate agent decisions.

After those rehearsals, report-action wording was clarified from the actual tap, cache invalidation, capture and email call path. The published cases also make their fixture prerequisites explicit. Those clarifications received source and document review; they were not rerun as fresh agent trials.

This change reuses [INV-06] and the existing scanners. It adds no semantic classifier or domain-runtime abstraction and contributes no glossary edits. The report repair used by the evaluation fixtures has its own decision and delivery scope.
