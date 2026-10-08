---
title: Glossary Change Routing
status: implemented
category: process
date: 2026-10-08
---

# Glossary Change Routing

## Context

A workflow that requires a glossary edit for every scheduling or device change treats execution rules as definitions and creates approval requests even when concept meanings remain stable. The same synchronization trigger in root and backend directives duplicates policy. Avoid-term checks provide no semantic validation of glossary entries.

## Contract

- [INV-06](../../../../CODING_STANDARDS.md#1-core-invariants) owns the concept-impact branches. Root and backend directives point to it instead of repeating an unconditional synchronization requirement.
- The [documentation routing rules](../../../skills/mower-doc/references/doc-hierarchy.md#routing-rules) distinguish concept identity from behavioral guarantees, implementation contracts and developer procedures. Definition constraints include the boundaries that identify a concept.
- A justified unchanged-concept review completes the assessment without glossary edits. A changed definition requires an exact bilingual proposal and [explicit glossary approval](../../../../AGENTS.md#4-global-execution-constraints) before writing it, including when the canonical name remains unchanged.
- Review reports record the chosen route and its reason. Existing glossary content supplies definitions rather than a placement precedent for new operational rules.
- Automated success reports only note-format, relative-link and Avoid-term checks. Concept changes, document placement and glossary approval remain review responsibilities.

## Verification

`arknights_mower/tests/verify_governance_tests.py` checks the bounded success report and verifies that each failed gate returns failure while the remaining checks still run. The [review recipe](../../../../docs/cookbook/review-glossary-impact.md) supplies six cases covering stable concepts, a new concept, an unchanged name with a changed boundary and a numeric setting change. These cases require semantic review; the unit suite does not claim to evaluate agent decisions.

This change reuses [INV-06] and the existing scanners. It adds no semantic classifier or runtime abstraction and leaves glossary contents unchanged.
